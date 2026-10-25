"""atlas wiki: the cards as a wiki in your browser, served from this Mac only (127.0.0.1).

    atlas wiki            start it if needed and open it (bare `atlas` starts it quietly too)
    atlas wiki --stop     stop it
    python -m atlas_cli.wiki --serve    run it in the foreground (what `atlas wiki` starts)

Standard library only (http.server). It refuses requests for any other host name (DNS rebinding) and
any form post from another site: every form carries a token minted when the server starts, and the
Origin must be this server. Pages are rendered with markdown's raw HTML off and a strict CSP.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
import pathlib
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import core as A
from ..storage import locked, atomic_write
from . import actions as X
from . import render as R
from . import views as V

PKG = pathlib.Path(__file__).resolve().parent.parent
TOKEN = secrets.token_urlsafe(24)
FLASH: dict[str, str] = {}
WRITE = threading.Lock()
GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")


def code_version() -> str:
    """Changes whenever atlas's code does, so `atlas wiki` can restart a server running older code."""
    h = hashlib.sha1()
    for p in sorted(PKG.rglob("*")):
        if p.suffix in (".py", ".html") and "__pycache__" not in p.parts:
            h.update(p.relative_to(PKG).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


VERSION = code_version()


def port() -> int:
    return int(os.environ.get("ATLAS_WIKI_PORT") or A.CFG.get("wiki_port", 8788))


def url(path: str = "/") -> str:
    return f"http://localhost:{port()}{path}"


def page_path(c) -> str:
    return R.page_url(c)


# ── the server ───────────────────────────────────────────────────────────────

class Stopping(RuntimeError):
    pass


class WikiServer(ThreadingHTTPServer):
    """Only admitted mutations delay shutdown; idle HTTP readers remain daemon workers."""
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self.instance = secrets.token_hex(16)
        self.writes = threading.Condition()
        self.active_writes = 0
        self.stopping = False
        super().__init__(*args, **kwargs)

    @contextmanager
    def mutation(self):
        with self.writes:
            if self.stopping:
                raise Stopping("The wiki is stopping; reload after it restarts.")
            self.active_writes += 1
        try:
            yield
        finally:
            with self.writes:
                self.active_writes -= 1
                self.writes.notify_all()

    def stop_mutations(self):
        with self.writes:
            self.stopping = True

    def drain(self):
        self.stop_mutations()
        with self.writes:
            self.writes.wait_for(lambda: self.active_writes == 0)

    def stop(self):
        self.stop_mutations()
        self.shutdown()


class Handler(BaseHTTPRequestHandler):
    server_version = "atlas-wiki"
    sys_version = ""

    def log_message(self, format, *args):         # quiet; errors go to the log through _error
        pass

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in (f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}")

    def _send(self, status: int, body: bytes, ctype: str, nonce: str = "", extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy",
                             f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
                             "img-src data: 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; "
                             "frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _page(self, snap, view, status=200):
        if view is None:
            view = V.not_found(snap)
            status = 404
        title, main, active, query = view
        nonce = secrets.token_urlsafe(12)
        self._send(status, V.document(snap, title, main, active, query, nonce).encode(), "text/html; charset=utf-8", nonce)

    def _redirect(self, location: str, notice: str = ""):
        if notice:
            key = secrets.token_urlsafe(6)
            FLASH[key] = notice
            location += ("&" if "?" in location else "?") + f"n={key}"
        self._send(303, b"", "text/plain", extra={"Location": location})

    def _plain(self, status: int, text: str):
        self._send(status, text.encode(), "text/plain; charset=utf-8")

    def _error(self, ex: Exception):
        log = A.ROOT / ".state" / "wiki.log"
        with log.open("a") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} {self.command} {self.path}\n{traceback.format_exc()}\n")
        try:
            snap = self._snapshot()
            self._page(snap, ("Something broke", '<div class="titlebar"><h1>Something broke</h1></div>'
                              f'<p class="lead">The wiki hit an error: <code>{R.e(type(ex).__name__)}: {R.e(ex)}</code>. '
                              'The details are in <code>.state/wiki.log</code> in the atlas folder.</p>', "", ""), 500)
        except Exception:
            self._plain(500, f"atlas wiki error: {ex}")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            return self._plain(421, "atlas wiki answers only to localhost")
        try:
            self._get()
        except Stopping as ex:
            self._plain(503, str(ex))
        except Exception as ex:                     # one bad page must not take the wiki down
            self._error(ex)

    def do_POST(self):
        if not self._host_ok():
            return self._plain(421, "atlas wiki answers only to localhost")
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://localhost:{self.server.server_port}", f"http://127.0.0.1:{self.server.server_port}"):
            return self._plain(403, "atlas wiki refuses forms posted from other sites")
        if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            return self._plain(403, "atlas wiki refuses forms posted from other sites")
        n = int(self.headers.get("Content-Length") or 0)
        if n > 2_000_000:
            return self._plain(413, "too large")
        raw = self.rfile.read(n).decode("utf-8", "replace")
        form = {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}
        if not secrets.compare_digest(form.get("token", ""), TOKEN):
            try:
                snap = self._snapshot()
            except Stopping as ex:
                return self._plain(503, str(ex))
            return self._page(snap, ("Reload the page", '<div class="titlebar"><h1>Reload the page</h1></div>'
                                     '<p class="lead">That page was opened before the wiki restarted, so its form is out of date. '
                                     'Go back, reload it, and try again. Nothing was changed.</p>', "", ""), 403)
        try:
            with self.server.mutation():
                with WRITE:
                    self._post(form)
        except Stopping as ex:
            self._plain(503, str(ex))
        except A.Conflict as ex:
            self._plain(409, str(ex))
        except Exception as ex:
            self._error(ex)

    def _snapshot(self):
        # A snapshot synchronizes external edits into history; drain just this write window.
        with self.server.mutation():
            return R.Snap()

    # GET routes
    def _get(self):
        u = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(u.path)
        qs = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        if path == "/healthz":
            body = json.dumps({"app": "atlas-wiki", "version": VERSION, "pid": os.getpid(), "root": str(A.ROOT), "port": self.server.server_port, "instance": self.server.instance})
            return self._send(200, body.encode(), "application/json")
        if path == "/probe.gif":
            return self._send(200, GIF, "image/gif")
        snap = self._snapshot()
        snap.notice = FLASH.pop(qs.get("n", ""), "")
        if path == "/api/suggest":
            return self._send(200, json.dumps(V.suggest(snap, qs.get("q", ""))).encode(), "application/json")
        if path in ("/", "/index.html"):
            return self._page(snap, V.main_page(snap))
        if path == "/search":
            query = qs.get("q", "")
            if qs.get("go"):
                exact = snap.by_key.get(query.strip().lower())
                if exact:
                    return self._redirect(R.page_url(exact))
            return self._page(snap, V.search(snap, query))
        m = re.fullmatch(r"/wiki/([^/]+)(?:/(edit|history|links|rev|diff)(?:/([^/]+))?)?/?", path)
        if m:
            slug, tab, arg = m.groups()
            c = snap.by_slug.get(slug)
            if c is None:
                other = snap.by_key.get(slug.lower())
                if other:
                    return self._redirect(R.page_url(other) + (f"/{tab}" if tab else ""))
                return self._page(snap, V.missing(snap, slug), 404)
            if tab is None:
                return self._page(snap, V.article(snap, c))
            if tab == "edit":
                sec = qs.get("section")
                section = int(sec) if sec and sec.isdigit() else None
                return self._page(snap, V.edit(snap, c, section=section, base=X.digest(c["_raw"])))
            if tab == "history":
                return self._page(snap, V.history(snap, c))
            if tab == "links":
                return self._page(snap, V.links_page(snap, c))
            if tab == "rev" and arg:
                return self._page(snap, V.revision(snap, c, arg))
            if tab == "diff":
                return self._page(snap, V.diff(snap, c, qs.get("a", ""), qs.get("b", "current")))
        m = re.fullmatch(r"/host/([^/]*)", path)
        if m:
            return self._page(snap, V.host_page(snap, m.group(1)))
        m = re.fullmatch(r"/kind/([^/]+)", path)
        if m:
            return self._page(snap, V.kind_page(snap, m.group(1)))
        special = {"/special": V.special, "/special/all": V.all_pages, "/special/recent": V.recent,
                   "/special/attention": V.attention, "/special/retired": V.retired, "/special/wanted": V.wanted,
                   "/special/places": V.places, "/special/kinds": V.kinds}
        if path in special:
            return self._page(snap, special[path](snap))
        if path == "/special/random":
            import random
            pool = snap.active or snap.cards
            return self._redirect(R.page_url(random.choice(pool)) if pool else "/")
        if path == "/special/new":
            return self._page(snap, V.new_page(snap, {**_blank_new(), "title": qs["title"]}) if qs.get("title") else V.new_page(snap))
        return self._page(snap, None)

    # POST routes
    def _post(self, form):
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        snap = R.Snap()
        if path == "/special/new":
            return self._result(snap, X.create_page(snap, form))
        if path == "/special/check-all":
            return self._result(snap, X.check_all(snap))
        m = re.fullmatch(r"/wiki/([^/]+)/(edit|do|restore)", path)
        if m and m.group(1) in snap.by_slug:
            c = snap.by_slug[m.group(1)]
            fn = {"edit": X.save_edit, "do": X.do_action, "restore": X.restore}[m.group(2)]
            return self._result(snap, fn(snap, c, form))
        return self._page(snap, None)

    def _result(self, snap, result):
        if result[0] == "redirect":
            return self._redirect(result[1], result[2])
        snap.notice = ""
        return self._page(snap, result[1], 200)


def _blank_new() -> dict:
    v = {k: "" for k in ("title", "kind", "host", "where", "what", "why", "source", "entry", "check", "links", "summary")}
    v.update(personal="yes", confidence="guess", body=A.parse(A.ROOT / "templates" / "card.md")["_body"].lstrip("\n"))
    return v


def serve() -> None:
    R.TOKEN = TOKEN
    A.load()  # Complete any interrupted lifecycle move before admitting requests.
    srv = WikiServer(("127.0.0.1", port()), Handler)
    metadata = {"app": "atlas-wiki", "version": VERSION, "pid": os.getpid(),
                "root": str(A.ROOT), "port": srv.server_port, "instance": srv.instance}
    with locked(A.ROOT):
        atomic_write(A.ROOT / ".state/wiki-server.json", json.dumps(metadata))
    signal.signal(signal.SIGTERM, lambda *a: threading.Thread(target=srv.stop, daemon=True).start())
    print(f"atlas wiki on {url()} (pid {os.getpid()}, code {VERSION})", flush=True)
    try:
        srv.serve_forever()
    finally:
        srv.drain()
        srv.server_close()
        with locked(A.ROOT):
            path = A.ROOT / ".state/wiki-server.json"
            if path.is_file() and json.loads(path.read_text()) == metadata:
                atomic_write(path, json.dumps({**metadata, "stopped": True}))


# ── starting and stopping it from the CLI ────────────────────────────────────

def _probe(bound_port, timeout):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{bound_port}/healthz", timeout=timeout) as r:
            data = json.loads(r.read())
            return {**data, "port": bound_port} if data.get("app") == "atlas-wiki" else {"app": "other"}
    except (OSError, ValueError):
        return None


def health(timeout: float = 0.6) -> dict | None:
    """Discover this inventory's existing listener even after wiki_port changes."""
    path = A.ROOT / ".state/wiki-server.json"
    if path.is_file():
        try:
            meta = json.loads(path.read_text())
            bound = int(meta["port"])
            if not 1 <= bound <= 65535:
                raise ValueError("invalid port")
        except (ValueError, KeyError, TypeError) as ex:
            raise RuntimeError(f"Invalid wiki server metadata: {ex}") from ex
        old = _probe(bound, timeout)
        if old and old.get("root") == str(A.ROOT) and old.get("pid") == meta.get("pid"):
            return old
    return _probe(port(), timeout)


def start(wait: bool = True) -> int:
    log = A.ROOT / ".state" / "wiki.log"
    log.parent.mkdir(exist_ok=True)
    env = {**os.environ, "ATLAS_DIR": str(A.ROOT)}
    with log.open("ab") as out:
        p = subprocess.Popen([sys.executable, "-m", "atlas_cli.wiki", "--serve"], stdin=subprocess.DEVNULL,
                             stdout=out, stderr=out, start_new_session=True, cwd=str(pathlib.Path.home()), env=env)
    if not wait:
        return p.pid
    for _ in range(80):
        time.sleep(0.1)
        h = health()
        if h and h.get("pid") == p.pid:
            return p.pid
        if p.poll() is not None:
            tail = log.read_text(errors="replace").strip().splitlines()[-1:] or ["no output"]
            raise RuntimeError(f"the wiki did not start: {tail[0]}")
    raise RuntimeError("the wiki did not answer within 8 seconds; see .state/wiki.log in the atlas folder")


def stop() -> bool:
    h = health()
    if not h or h.get("app") != "atlas-wiki":
        return False
    if h.get("root") != str(A.ROOT):
        raise RuntimeError("That wiki serves another inventory; it was not stopped.")
    try:
        os.kill(int(h["pid"]), signal.SIGTERM)
    except ProcessLookupError:
        return False
    for _ in range(80):
        time.sleep(0.1)
        # The listener can disappear while writes drain, and an exited server can remain
        # an unreaped zombie. Only this instance's post-drain/post-close marker suffices.
        try:
            meta = json.loads((A.ROOT / ".state/wiki-server.json").read_text())
            if (h.get("instance") and meta.get("stopped") is True and
                    all(meta.get(key) == h.get(key) for key in ("app", "root", "pid", "port", "instance"))):
                return True
        except (OSError, ValueError):
            pass
        try:
            os.kill(int(h["pid"]), 0)
        except ProcessLookupError:
            return True
    raise RuntimeError("The wiki is still draining active writes; it has not stopped yet.")


def ensure(wait: bool = True) -> str:
    """Make sure a wiki running this code, on these cards, is up. Returns what happened."""
    h = health()
    if h and h.get("app") != "atlas-wiki":
        raise RuntimeError(f"port {port()} is used by something else; set wiki_port in atlas.json")
    if h and h.get("root") != str(A.ROOT):
        raise RuntimeError("The configured port serves another inventory; choose a different wiki_port.")
    if h and h.get("version") == VERSION and h.get("root") == str(A.ROOT) and h.get("port") == port():
        return "running"
    if h:
        stop()
        start(wait)
        return "restarted for the current code and configured port"
    start(wait)
    return "started"


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--serve" in argv:
        serve()
    else:
        print(__doc__)
