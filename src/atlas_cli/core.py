"""atlas core: cards, checks, search, the generated pages. No terminal output here."""
import ctypes
import hashlib
import datetime as dt, html, json, os, pathlib, re, secrets, shutil, subprocess, sys, signal

from . import history as H
from .storage import locked, atomic_write, fsync_dir, read_text
from functools import wraps

def load_config(root):
    """Load portable defaults and optional machine-only overrides consistently."""
    cfg = json.loads((root / "atlas.json").read_text())
    local = root / "atlas.local.json"
    if local.is_file():
        cfg.update(json.loads(local.read_text()))
    return cfg


ROOT = pathlib.Path(os.environ.get("ATLAS_DIR", pathlib.Path.home() / "Developer" / "atlas")).expanduser()
CFG = load_config(ROOT)
STATE = ROOT / ".state" / "checks.json"
FOLDERS = {"inbox": "Draft", "cards": "Active", "retired": "Retired"}
FIELDS = ["id", "title", "kind", "host", "where", "what", "why", "source", "entry", "check",
          "links", "notes", "confidence", "confirmed"]
REQUIRED = ["title", "kind", "host", "where", "what", "why", "source", "check"]
TODAY = dt.date.today()
HOME = pathlib.Path.home()


def expand(p):
    return pathlib.Path(os.path.expanduser(p))


# ---------- cards: a small, strict frontmatter format (key: value, lists as [a, b]) ----------

def _parts(text, separator=None):
    """Split commas/comments only outside quoted strings (also reads legacy plain values)."""
    quote, escape, start, out = None, False, 0, []
    for i, ch in enumerate(text):
        if escape:
            escape = False
        elif quote and ch == "\\" and quote == '"':
            escape = True
        elif quote:
            if ch == quote:
                quote = None
        elif ch in "'\"" and (i == 0 or text[i-1] in " \t[:,"):
            quote = ch
        elif separator and ch == separator:
            out.append(text[start:i].strip())
            start = i + 1
        elif not separator and ch == "#" and i >= 2 and text[i-2:i] == "  ":
            return text[:i].rstrip()
    if separator:
        out.append(text[start:].strip())
        return out
    return text.rstrip()


def _scalar(text):
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        if text[0] == '"':
            try:
                value = json.loads(text)
                if isinstance(value, str):
                    return value
            except ValueError:
                pass  # Old cards used surrounding quotes without JSON escapes.
        return text[1:-1]
    return text


def parse(path):
    return parse_text(read_text(path), path)


def parse_text(text, path):
    """Parse a single captured version; `_raw` binds later writes to this exact snapshot."""
    path = pathlib.Path(path)
    m = re.match(r"---\r?\n(.*?)\r?\n---(?:\r?\n)?(.*)", text, re.S)
    if not m:
        raise ValueError(f"{path}: no frontmatter")
    meta = {}
    for line in re.split(r"\r?\n", m.group(1)):
        line = _parts(line)
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        k, sep, v = line.partition(":")
        if not sep or not k.strip():
            raise ValueError(f"{path}: invalid frontmatter line {line!r}")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [_scalar(x) for x in _parts(v[1:-1], ",") if x]
        else:
            v = _scalar(v)
        meta[k.strip()] = v
    for k in ("links", "notes", "aliases"):
        if k in ("links", "notes"):
            meta.setdefault(k, [])
        if isinstance(meta.get(k), str):
            meta[k] = [meta[k]] if meta[k] else []
    meta.update(_raw=text, _body=m.group(2), _path=path, _slug=path.stem,
                _personal=path.parent.name == "personal")
    meta["_folder"] = path.parent.parent.name if meta["_personal"] else path.parent.name
    return meta


def dump(card):
    def quoted(v):
        text = json.dumps(v, ensure_ascii=False)
        for ch in "\u0085\u2028\u2029":
            text = text.replace(ch, "\\u%04x" % ord(ch))
        return text
    def val(v):
        if isinstance(v, list):
            return quoted(v)
        v = str(v)
        if v != v.strip() or any(ch in v for ch in "\n\r\t\\'\"[]{}") or any(ord(ch) < 32 or ch in "\u0085\u2028\u2029" for ch in v) or ": " in v or " #" in v:
            return quoted(v)
        return v
    keys = FIELDS + [k for k in card if not k.startswith("_") and k not in FIELDS]
    head = "\n".join(f"{k}: {val(card[k])}".rstrip() for k in keys if k in card)
    return f"---\n{head}\n---\n{card.get('_body', '')}"


def load(folders=("inbox", "cards", "retired")):
    with locked(ROOT):
        _recover_save()
        _recover_move()
        cards = []
        for f in folders:
            for p in sorted((ROOT / f).glob("*.md")) + sorted((ROOT / f / "personal").glob("*.md")):
                cards.append(parse(p))
        return cards


def ordered(cards):
    """Every card in map order: by place, then title; drafts after active cards. Numbers come from here."""
    hosts = list(CFG["hosts"])
    rank = lambda h: hosts.index(h) if h in hosts else len(hosts)
    return sorted([c for c in cards if c["_folder"] != "retired"],
                  key=lambda c: (rank(c.get("host", "")), c.get("host", ""), c["_folder"] == "inbox", c["title"].lower()))


def search(query, cards=None):
    """Cards matching a number from the map, an id or file name, or words in the title (then anywhere)."""
    cards = cards if cards is not None else load()
    q = query.strip().lower()
    if q.isdigit():
        lst = ordered(cards)
        n = int(q)
        return [lst[n - 1]] if 1 <= n <= len(lst) else []
    exact = [c for c in cards if q in (c.get("id", "").lower(), c["_slug"])]
    if exact:
        return exact
    words = q.split()
    title = [c for c in cards if all(w in (c["title"] + " " + c["_slug"]).lower() for w in words)]
    if title:
        return title
    return [c for c in cards if all(w in c["_raw"].lower() for w in words)]


class NoMatch(Exception):
    pass


class Ambiguous(Exception):
    def __init__(self, query, hits):
        super().__init__(query)
        self.query, self.hits = query, hits


def numbers(cards):
    """slug -> number on the map."""
    return {c["_slug"]: i for i, c in enumerate(ordered(cards), 1)}


def find(ident, cards=None):
    """Exactly one card, or NoMatch / Ambiguous (with the candidates)."""
    cards = cards if cards is not None else load()
    hits = search(ident, cards)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise NoMatch(ident)
    num = numbers(cards)
    raise Ambiguous(ident, sorted(hits, key=lambda c: num.get(c["_slug"], 999)))


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60]


# ---------- checks ----------

def state():
    return json.loads(STATE.read_text()) if STATE.is_file() else {}


def _kill_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def _check_binding(c):
    """Command and captured card bytes/path identify what was actually checked."""
    digest = lambda text: hashlib.sha256(text.encode('utf-8')).hexdigest()
    return dict(command=digest(c.get('check', '')),
                snapshot=digest(str(c['_path'].relative_to(ROOT)) + '\0' + c['_raw']))


def check_result(c, st):
    result = st.get(c.get('id'))
    if not result or any(result.get(k) != v for k, v in _check_binding(c).items()):
        return None
    return result


def _current_check(c, identity=None):
    # Re-read under the cross-process inventory lock; never run caller-held stale commands.
    current = next((x for x in load() if x.get('id') == c.get('id')), None)
    if (current is None or _check_binding(current) != _check_binding(c) or
            (identity is not None and _identity(current['_path']) != identity)):
        return None
    return current


def run_checks(cards, on_each=None, accept_result=None):
    """Run each card's check; on_each(card, ok, out) after each one. Results go to .state/checks.json."""
    updates = {}
    for c in cards:
        cmd = c.get("check", "")
        if not cmd:
            continue
        with locked(ROOT):
            current = _current_check(c)
            if current is None: continue
            identity = _identity(current['_path'])
            runs = ROOT / '.state/check-generation.json'
            generation = (json.loads(read_text(runs)) if runs.exists() else 0) + 1
            atomic_write(runs, json.dumps(generation))
            binding = _check_binding(current)
        try:
            r = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, cwd=HOME, start_new_session=True)
            try:
                stdout, stderr = r.communicate(timeout=CFG.get("check_timeout", 15))
            except BaseException:
                _kill_group(r.pid, signal.SIGTERM)
                try:
                    r.communicate(timeout=0.2)
                except BaseException:
                    pass
                finally:
                    _kill_group(r.pid, signal.SIGKILL)
                try:
                    r.communicate(timeout=1)
                except BaseException:
                    # A broken communicate() must not prevent reaping the direct child,
                    # nor replace the original cancellation/communication exception.
                    r.wait(timeout=1)
                raise
            ok, out = r.returncode == 0, (stdout + stderr).strip()
        except subprocess.TimeoutExpired:
            ok, out = False, f"timed out after {CFG.get('check_timeout', 15)}s"
        result = {"ok": ok, "at": dt.datetime.now().isoformat(timespec="minutes"),
                       "out": out.splitlines()[-1][:200] if out else ""}
        if accept_result is None or accept_result(c, result):
            updates[c["id"]] = (c, identity, {**result, **binding, "generation": generation})
        if on_each:
            on_each(c, ok, result["out"])
    with locked(ROOT):
        st = state()
        for cid, (c, identity, result) in updates.items():
            if (_current_check(c, identity) is not None and
                    result['generation'] > st.get(cid, {}).get('generation', 0)):
                st[cid] = result
        atomic_write(STATE, json.dumps(st, indent=1) + "\n")
        # Explicit callers must not interpret an unmatched historical success as
        # the outcome of this run when the card changed during execution.
        current = {}
        for c in load():
            result = check_result(c, st)
            if result is not None:
                current[c["id"]] = result
        return current


def status(c, st):
    """(word, state) for display. state is ok | fail | none | draft | retired."""
    if c["_folder"] == "retired":
        return "Retired", "retired"
    s = check_result(c, st)
    if c["_folder"] == "inbox":
        return "Draft", "draft"
    if not c.get("check"):
        return "No check", "none"
    if not s:
        return "Not checked", "none"
    return ("OK", "ok") if s["ok"] else ("Failing", "fail")


def stale(c):
    try:
        return (TODAY - dt.date.fromisoformat(c.get("confirmed", ""))).days > CFG.get("stale_days", 30)
    except ValueError:
        return True


def attention(cards, st):
    """Most urgent first: failing checks, drafts waiting, guesses, stale confirmations. One row per card."""
    rows = {}
    for c in cards:
        word, s = status(c, st)
        why, rank = [], 9
        res = check_result(c, st)
        if res and not res["ok"]:
            why.append("not ok" + (f": {res['out']}" if res["out"] else ", its check fails")); rank = 0
        if s == "draft":
            why.append("new, not confirmed yet"); rank = min(rank, 1)
        elif s == "none":
            why.append("no passing check yet"); rank = min(rank, 2)
        if c["_folder"] == "cards" and c.get("confidence") == "guess":
            why.append("still a guess"); rank = min(rank, 3)
        elif c["_folder"] == "cards" and stale(c):
            why.append(f"not confirmed since {c.get('confirmed') or 'ever'}")
            rank = min(rank, 4)
        if why:
            rows[c["id"]] = (rank, c, "; ".join(why))
    return sorted(rows.values(), key=lambda x: (x[0], x[1]["title"]))


# ---------- build: ATLAS.md ----------

def host_name(h):
    return CFG["hosts"].get(h, h)


def linkname(c):
    target = c["_path"].relative_to(ROOT).with_suffix("").as_posix()
    return f"[[{target}|{c['title']}]]"


def build_md(cards, st):
    active = [c for c in cards if c["_folder"] != "retired"]
    counts = {k: sum(1 for c in active if status(c, st)[1] == k) for k in ("ok", "fail", "none", "draft")}
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = ["# Atlas", "",
         "What runs where, and why. One card per thing in `cards/`; this page is built from them.", "",
         f"_Updated {now} by `atlas check`. Edit the cards, not this file._", "",
         f"{len(active) - counts['draft']} cards: {counts['ok']} OK, {counts['fail']} failing, "
         f"{counts['none']} without a passing check. {counts['draft']} draft(s) in the inbox.", ""]
    att = attention(active, st)
    if att:
        L += ["## Needs a look", ""]
        L += [f"- [ ] **{linkname(c)}** `{c['id']}`: {why}" for _, c, why in att]
        L.append("")
    L += ["## By place", ""]
    by_host = {}
    for c in active:
        by_host.setdefault(c.get("host", ""), []).append(c)
    order = list(CFG["hosts"]) + sorted(h for h in by_host if h not in CFG["hosts"])
    for h in order:
        if h not in by_host:
            continue
        L += [f"### {host_name(h)}", ""]
        for c in sorted(by_host[h], key=lambda c: (c["_folder"] == "inbox", c["title"])):
            word, _ = status(c, st)
            L.append(f"- **{linkname(c)}** · {c.get('kind', '')} · {word} · `{c['id']}`")
            L.append(f"  {c.get('what', '')} Where: `{c.get('where', '')}`.")
            if c.get("why"):
                L.append(f"  Why: {c['why']}")
        L.append("")
    edges = [(c, l) for c in active for l in c.get("links", [])]
    if edges:
        idx = {x.get("id"): x for x in active} | {x["_slug"]: x for x in active}
        L += ["## Connections", "", "```mermaid", "flowchart LR"]
        for h in order:
            group = by_host.get(h)
            if group:
                L.append(f'  subgraph {re.sub(r"[^A-Za-z0-9]", "_", h)}["{host_name(h)}"]')
                L += [f'    {c["id"].replace("-", "_")}["{c["title"]}"]' for c in group]
                L.append("  end")
        for c, l in edges:
            if l in idx:
                L.append(f'  {c["id"].replace("-", "_")} --> {idx[l]["id"].replace("-", "_")}')
        L += ["```", ""]
    retired = [c for c in cards if c["_folder"] == "retired"]
    if retired:
        L += ["## Retired", ""] + [f"- {linkname(c)} `{c['id']}`: {c.get('retired_reason', '')}" for c in retired] + [""]
    (ROOT / "ATLAS.md").write_text("\n".join(L))


# ---------- build: the life-admin page, which forwards to the wiki ----------

def wiki_url(path="/"):
    port = os.environ.get("ATLAS_WIKI_PORT") or CFG.get("wiki_port", 8788)
    return f"http://localhost:{port}{path}"


def build_html(cards, st):
    """The life-admin hub's Atlas tile opens this page. It forwards to the wiki when the wiki is running,
    and says how to start it when it is not. Built from the dashboard template, so it passes check_theme."""
    out, tpl = CFG.get("html_out"), CFG.get("template")
    if not out or not tpl or not expand(tpl).is_file():
        return None
    out, tpl = expand(out), expand(tpl).read_text()
    prefix = tpl[: tpl.index("<!-- @ds-mark end -->") + len("<!-- @ds-mark end -->")]
    prefix = re.sub(r"<title>.*?</title>", "<title>Atlas</title>", prefix, count=1)
    url = html.escape(wiki_url())
    page = prefix + f"""
    <a class="brand" href="index.html">Life admin</a><span class="crumb">/ atlas</span>
  </div>
</header>
<main class="wrap">
  <h2>Atlas</h2>
  <p class="lead" id="msg">Opening the atlas wiki at <a href="{url}">{url}</a>.</p>
  <p id="down" hidden>The wiki is not running. In a terminal, type <code>atlas wiki</code>: it starts the wiki and opens it here.</p>
</main>
<footer class="site"><div class="wrap">Atlas lives in <code>~/Developer/atlas</code>; this page only forwards to its wiki.</div></footer>
<script>
const url = "{url}";
const probe = new Image();
probe.onload = () => location.replace(url);
probe.onerror = () => {{
  document.getElementById("msg").textContent = "The atlas wiki is not running.";
  document.getElementById("down").hidden = false;
}};
probe.src = url + "probe.gif?" + Date.now();
</script>
</body>
</html>
"""
    out.write_text(page)
    return out


# ---------- operations (no printing; the CLI presents the results) ----------

def place(c, folder):
    """Where a card goes in `folder`, keeping it personal (out of git) if it was."""
    d = ROOT / folder / ("personal" if c["_personal"] else "")
    d.mkdir(parents=True, exist_ok=True)
    return d / c["_path"].name


class Conflict(ValueError):
    """A safe refusal: reload the card before retrying."""


def transaction(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        with locked(ROOT):
            _recover_save()
            _recover_move()
            return fn(*args, **kwargs)
    return run


def validate_snapshot(c):
    path = c["_path"]
    if not path.is_file() or c.get("_raw") != read_text(path):
        raise Conflict("This card changed since it was read; reload it before retrying.")
    if parse(path).get("id") != c.get("id"):
        raise Conflict("The card identity changed; reload it before retrying.")


def check_title(title, own_path=None):
    key = title.strip().lower()
    for other in load():
        if other["_path"] == own_path:
            continue
        keys = [other["title"], other["_slug"], other.get("id", ""), *(other.get("aliases") or [])]
        if key in [k.lower() for k in keys] or slugify(title) == other["_slug"]:
            raise Conflict(f"A page called {title!r} already exists (or is an alias of {other['title']!r}).")


def check_names(candidate, own_path):
    """The resolver shares one case-insensitive title/alias/slug/id namespace."""
    names = [candidate.get('title', ''), *(candidate.get('aliases') or [])]
    if not all(isinstance(name, str) for name in names):
        raise ValueError("Page titles and aliases must be text.")
    check_title(candidate.get('title', ''), own_path)
    keys = {name.lower() for name in names if name}
    for other in load():
        if other['_path'] == own_path: continue
        owned = [other['title'], other['_slug'], other.get('id', ''), *(other.get('aliases') or [])]
        collisions = keys.intersection(name.lower() for name in owned)
        if collisions:
            raise Conflict(f"Page name or alias {sorted(collisions)[0]!r} is already owned by {other['title']!r}.")


@transaction
def save(c, summary, by="cli", text=None, personal=None):
    """Claim the actual displaced inode before exclusively publishing a replacement."""
    validate_snapshot(c)
    text = dump(c) if text is None else text
    dest = move_destination(c, c["_folder"], personal)
    parsed = parse_text(text, dest)
    if parsed.get("id") != c.get("id"):
        raise ValueError("A save cannot change the card ID.")
    check_names(parsed, c["_path"])
    _begin_save(c, dest, text, summary, by)
    c.clear()
    c.update(parsed)


@transaction
def new_card(title, kind, host, personal=False, confidence="believed", body=None, by="cli", summary="created", **fields):
    check_title(title)
    slug = slugify(title)
    if not slug:
        raise ValueError("a card needs a title with letters or digits")
    if any(c["_slug"] == slug for c in load()):
        raise ValueError(f"a card named {slug} already exists")
    path = ROOT / "inbox" / ("personal" if personal else "") / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    tpl = parse(ROOT / "templates" / "card.md")
    card = {k: tpl.get(k, "") for k in FIELDS}
    card.update(id="a-" + secrets.token_hex(3), title=title, kind=kind, host=host, confidence=confidence,
                confirmed="", links=fields.pop("links", []) or [], notes=[])
    card.update({k: v for k, v in fields.items() if v})
    card["_body"] = tpl["_body"] if body is None else body
    text = dump(card)
    parse_text(text, path)  # Refuse malformed output before any card publication.
    atomic_write(path, text)
    H.record(ROOT, card["id"], read_text(path), summary, by)
    return parse(path)


def promote(c, force=False, by="cli"):
    """inbox -> cards. Returns (dest, problem); problem is None on success."""
    if c["_folder"] != "inbox":
        return None, f"it is already in {c['_folder']}/"
    missing = [k for k in REQUIRED if not c.get(k)]
    st = run_checks([c]) if c.get("check") else state()
    with locked(ROOT):
        validate_snapshot(c)
    if not force:
        if missing:
            return None, "fill these first: " + ", ".join(missing)
        if not (check_result(c, st) or {}).get("ok"):
            return None, "its check does not pass yet"
    c["confirmed"] = TODAY.isoformat()
    if c.get("confidence") in ("", "guess") and not missing:
        c["confidence"] = "confirmed"
    dest = _move(c, "cards", "promoted from the inbox to the map", by)
    return dest, None


def move_destination(c, folder, personal=None):
    dest = ROOT / folder / ("personal" if (c["_personal"] if personal is None else personal) else "") / c["_path"].name
    if dest != c["_path"] and dest.exists():
        raise Conflict(f"Destination already exists: {dest.relative_to(ROOT)}; no cards were changed.")
    return dest


def _identity(path):
    st = path.stat()
    return [st.st_dev, st.st_ino]


def _move_path(name, staged=False):
    """Journal paths are confined to actual inventory card directories, without symlinks."""
    if not isinstance(name, str):
        raise ValueError("invalid move path")
    rel = pathlib.PurePosixPath(name)
    if (rel.is_absolute() or len(rel.parts) not in (2, 3) or rel.parts[0] not in FOLDERS or
            (len(rel.parts) == 3 and rel.parts[1] != 'personal') or
            '..' in rel.parts or rel.as_posix() != name):
        raise ValueError("move path escapes card directories")
    if staged:
        if not re.fullmatch(r'\.atlas-move-[0-9a-f]{32}', rel.name):
            raise ValueError("invalid move staging path")
    elif not rel.name.endswith('.md') or rel.name.startswith('.'):
        raise ValueError("invalid move card path")
    path = ROOT / name
    if path.resolve() != ROOT.resolve() / name:
        raise ValueError("symlink in move path")
    return path


def _move_matches(path, identity, text):
    return (not path.is_symlink() and path.is_file() and _identity(path) == identity and
            read_text(path) == text)


def _claim_path(name, card_path, leaf):
    """Claims live in private, exclusively created directories on the card filesystem."""
    if not isinstance(name, str):
        raise ValueError("invalid move claim")
    path = ROOT / name
    if (path.parent.parent != card_path.parent or path.name != leaf or
            not re.fullmatch(r'\.atlas-claim-[0-9a-f]{32}', path.parent.name) or
            path.relative_to(ROOT).as_posix() != name or
            path.resolve() != ROOT.resolve() / name or not path.parent.is_dir()):
        raise ValueError("invalid or escaping move claim")
    return path


def _read_move():
    """Validate durable intent and existing files; unknown artifacts always fail closed."""
    journal = ROOT / '.state/move.json'
    try:
        j = json.loads(read_text(journal))
        if j['version'] != 2 or not re.fullmatch(r'a-[0-9a-f]{6}', j['id']):
            raise ValueError("invalid move version or card ID")
        source, dest, stage = (_move_path(j['source']), _move_path(j['dest']), _move_path(j['stage'], True))
        claim = _claim_path(j['source_claim'], source, 'source')
        rollback = _claim_path(j['dest_claim'], dest, 'destination')
        if source == dest or stage.parent != dest.parent or j['phase'] != 'move':
            raise ValueError("invalid move destinations or pending rollback")
        for key in ('before', 'after', 'summary', 'by', 'at'):
            if not isinstance(j[key], str):
                raise ValueError("invalid move fields")
        for key in ('source_identity', 'stage_identity'):
            if not isinstance(j[key], list) or len(j[key]) != 2 or not all(type(n) is int for n in j[key]):
                raise ValueError("invalid move identity")
        if any(parse_text(j[key], source).get('id') != j['id'] for key in ('before', 'after')):
            raise ValueError("move card ID changed")
        if not _move_matches(stage, j['stage_identity'], j['after']):
            raise ValueError("move staging file changed")
        if os.path.lexists(rollback):
            raise ValueError("unexpected rollback claim")
        if os.path.lexists(claim):
            if not _move_matches(claim, j['source_identity'], j['before']) or os.path.lexists(source):
                raise ValueError("move source claim changed or original name recreated")
        elif not _move_matches(source, j['source_identity'], j['before']):
            raise ValueError("move source changed or missing")
        if dest.exists() and not _move_matches(dest, j['stage_identity'], j['after']):
            raise ValueError("move destination changed or already owned")
        return j, source, dest, stage, claim, rollback
    except (OSError, ValueError, KeyError, TypeError) as ex:
        raise Conflict(f"Interrupted card move needs reconciliation; no unknown files were removed: {ex}") from ex


def _clear_move(stage):
    # Retain stage and claims: an outside editor can still hold any inode open.
    journal = ROOT / '.state/move.json'
    journal.unlink()
    fsync_dir(journal.parent)


def _rename_claim(source, claim):
    """Atomic rename without replacement, including a concurrent claim collision."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        args = (os.fsencode(source), os.fsencode(claim), 0x00000004)  # RENAME_EXCL
    elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        args = (-100, os.fsencode(source), -100, os.fsencode(claim), 1)  # AT_FDCWD, RENAME_NOREPLACE
    else:
        raise Conflict("Atomic exclusive rename unavailable; move needs reconciliation.")
    rename.restype = ctypes.c_int
    if rename(*args):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(source), None, str(claim))


def _claim_file(path, claim):
    # The precheck is diagnostic only; exclusive rename enforces ownership.
    # Claims are journaled before capture and retained even after validation.
    if os.path.lexists(claim):
        raise Conflict(f"Move claim already occupied; needs reconciliation: {claim}")
    _rename_claim(path, claim)
    fsync_dir(claim.parent)
    fsync_dir(path.parent)


def _restore_claim(claim, path):
    # Keep the backup and exclusively publish the captured inode. A newer original
    # name always wins. No unlink/replace follows a content or ownership check.
    if claim.is_symlink() or not claim.is_file():
        raise Conflict(f"Unknown move claim retained for reconciliation: {claim}")
    try:
        os.link(claim, path, follow_symlinks=False)
    except FileExistsError:
        pass
    fsync_dir(path.parent)


def _rollback_move(j, source, dest, stage, claim, rollback):
    # Persist this first: a crash during rollback must never replay forward intent.
    j['phase'] = 'rollback'
    atomic_write(ROOT / '.state/move.json', json.dumps(j, ensure_ascii=False))
    if os.path.lexists(claim):
        _restore_claim(claim, source)
    if os.path.lexists(dest):
        _claim_file(dest, rollback)
        if not _move_matches(rollback, j['stage_identity'], j['after']):
            _restore_claim(rollback, dest)
            raise Conflict("Move rollback captured a changed destination; retained for reconciliation.")
    if (not _move_matches(source, j['source_identity'], j['before']) or
            (os.path.lexists(claim) and not _move_matches(claim, j['source_identity'], j['before']))):
        raise Conflict("Move captured an external source edit; backups retained for reconciliation.")
    _clear_move(stage)


def _recover_move():
    """Finish one inventory-locked move without ever unlinking a card inode."""
    if not (ROOT / '.state/move.json').exists():
        return
    j, source, dest, stage, claim, rollback = _read_move()
    try:
        if not dest.exists():
            os.link(stage, dest)
            fsync_dir(dest.parent)
        if not os.path.lexists(claim):
            _claim_file(source, claim)
        # Validate the inode actually removed from the original name, rather than
        # checking the name and subsequently deleting whatever an editor put there.
        if not _move_matches(claim, j['source_identity'], j['before']) or os.path.lexists(source):
            raise Conflict("Move source changed at claim boundary; needs reconciliation.")
    except Exception:
        _rollback_move(j, source, dest, stage, claim, rollback)
        raise
    old = H.entries(ROOT, j['id'])
    entry = {k: j[k] for k in ('at', 'by', 'summary')}
    entry['text'] = j['after']
    if not old or any(old[-1].get(k) != v for k, v in entry.items()):
        H.record(ROOT, j['id'], j['after'], j['summary'], j['by'], at=j['at'], force=True)
    _clear_move(stage)


def _clear_save():
    # Retain all captured inodes: an editor may still have one open.
    path = ROOT / '.state/save.json'
    path.unlink()
    fsync_dir(path.parent)


def _read_save():
    try:
        j = json.loads(read_text(ROOT / '.state/save.json'))
        if j['version'] != 1 or j['phase'] != 'save' or not re.fullmatch(r'a-[0-9a-f]{6}', j['id']):
            raise ValueError("invalid save intent or pending rollback")
        source, dest, stage = _move_path(j['source']), _move_path(j['dest']), _move_path(j['stage'], True)
        claim = _claim_path(j['source_claim'], source, 'source')
        rollback = _claim_path(j['dest_claim'], dest, 'destination')
        if stage.parent != dest.parent:
            raise ValueError("invalid save staging directory")
        for key in ('before', 'after', 'summary', 'by', 'at'):
            if not isinstance(j[key], str): raise ValueError("invalid save fields")
        for key in ('source_identity', 'stage_identity'):
            if not isinstance(j[key], list) or len(j[key]) != 2 or not all(type(n) is int for n in j[key]):
                raise ValueError("invalid save identity")
        if any(parse_text(j[key], source).get('id') != j['id'] for key in ('before', 'after')):
            raise ValueError("save card ID changed")
        if not _move_matches(stage, j['stage_identity'], j['after']) or os.path.lexists(rollback):
            raise ValueError("save stage changed or unexpected rollback claim")
        if os.path.lexists(claim):
            if not _move_matches(claim, j['source_identity'], j['before']):
                raise ValueError("save source claim changed")
            if source != dest and os.path.lexists(source):
                raise ValueError("save original name recreated")
            if os.path.lexists(dest) and not _move_matches(dest, j['stage_identity'], j['after']):
                raise ValueError("save destination changed")
        elif not _move_matches(source, j['source_identity'], j['before']) or (dest != source and os.path.lexists(dest)):
            raise ValueError("save source changed or destination occupied")
        return j, source, dest, stage, claim, rollback
    except (OSError, ValueError, KeyError, TypeError) as ex:
        raise Conflict(f"Interrupted card save needs reconciliation; all artifacts retained: {ex}") from ex


def _rollback_save(j, source, dest, stage, claim, rollback):
    j['phase'] = 'rollback'
    atomic_write(ROOT / '.state/save.json', json.dumps(j, ensure_ascii=False))
    # With an in-place save the original name may now hold the published stage or
    # an unknown editor replacement. Capture either atomically, never unlink it.
    if os.path.lexists(claim):
        if os.path.lexists(dest):
            _claim_file(dest, rollback)
            if not _move_matches(rollback, j['stage_identity'], j['after']):
                _restore_claim(rollback, dest)
        _restore_claim(claim, source)
    if (not _move_matches(source, j['source_identity'], j['before']) or
            (os.path.lexists(claim) and not _move_matches(claim, j['source_identity'], j['before'])) or
            (os.path.lexists(rollback) and not _move_matches(rollback, j['stage_identity'], j['after']))):
        raise Conflict("Save captured an external edit; originals and backups retained for reconciliation.")
    _clear_save()


def _recover_save():
    """Recover under the inventory lock; history helpers never call back into load."""
    if not (ROOT / '.state/save.json').exists(): return
    j, source, dest, stage, claim, rollback = _read_save()
    try:
        if not os.path.lexists(claim): _claim_file(source, claim)
        if not _move_matches(claim, j['source_identity'], j['before']):
            raise Conflict("Save source changed at capture; needs reconciliation.")
        if source != dest and os.path.lexists(source):
            raise Conflict("Save original name recreated; needs reconciliation.")
        if not os.path.lexists(dest):
            os.link(stage, dest, follow_symlinks=False)
            fsync_dir(dest.parent)
        if (not _move_matches(dest, j['stage_identity'], j['after']) or
                not _move_matches(claim, j['source_identity'], j['before'])):
            raise Conflict("Save changed at publication; needs reconciliation.")
    except Exception:
        _rollback_save(j, source, dest, stage, claim, rollback)
        raise
    old = H.entries(ROOT, j['id'])
    entry = {k: j[k] for k in ('at', 'by', 'summary')}
    entry['text'] = j['after']
    if not old or any(old[-1].get(k) != v for k, v in entry.items()):
        H.record(ROOT, j['id'], j['after'], j['summary'], j['by'], at=j['at'], force=True)
    _clear_save()


def _begin_save(c, dest, text, summary, by):
    source = c['_path']
    _move_path(str(source.relative_to(ROOT)))
    _move_path(str(dest.relative_to(ROOT)))
    identity = _identity(source)
    mode = source.stat().st_mode & 0o777
    H.ensure_base(ROOT, c['id'], source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage = dest.parent / ('.atlas-move-' + secrets.token_hex(16))
    atomic_write(stage, text)
    stage.chmod(mode)
    with stage.open('rb') as stream: os.fsync(stream.fileno())
    claims = []
    for path, leaf in ((source, 'source'), (dest, 'destination')):
        directory = path.parent / ('.atlas-claim-' + secrets.token_hex(16))
        directory.mkdir(mode=0o700)
        fsync_dir(path.parent)
        claims.append(str((directory / leaf).relative_to(ROOT)))
    j = dict(version=1, phase='save', id=c['id'], source=str(source.relative_to(ROOT)),
             dest=str(dest.relative_to(ROOT)), stage=str(stage.relative_to(ROOT)),
             source_identity=identity, stage_identity=_identity(stage), source_claim=claims[0],
             dest_claim=claims[1], before=c['_raw'], after=text, summary=summary, by=by, at=H.now())
    atomic_write(ROOT / '.state/save.json', json.dumps(j, ensure_ascii=False))
    _recover_save()


@transaction
def _move(c, folder, summary, by, personal=None):
    validate_snapshot(c)
    dest = move_destination(c, folder, personal)
    if dest == c["_path"]:
        return dest
    source = c['_path']
    # Validate path scope before creating any move artifacts.
    _move_path(str(source.relative_to(ROOT)))
    _move_path(str(dest.relative_to(ROOT)))
    source_identity = _identity(source)
    H.ensure_base(ROOT, c.get("id"), source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = dump(c)
    parse_text(text, dest)
    stage = dest.parent / ('.atlas-move-' + secrets.token_hex(16))
    atomic_write(stage, text)
    stage.chmod(source.stat().st_mode & 0o777)
    with stage.open('rb') as stream:
        os.fsync(stream.fileno())
    claims = []
    for path, leaf in ((source, 'source'), (dest, 'destination')):
        directory = path.parent / ('.atlas-claim-' + secrets.token_hex(16))
        directory.mkdir(mode=0o700)
        fsync_dir(path.parent)
        claims.append(str((directory / leaf).relative_to(ROOT)))
    journal = {'version': 2, 'phase': 'move', 'source_claim': claims[0], 'dest_claim': claims[1], 'id': c['id'], 'source': str(source.relative_to(ROOT)),
               'dest': str(dest.relative_to(ROOT)), 'stage': str(stage.relative_to(ROOT)),
               'source_identity': source_identity, 'stage_identity': _identity(stage),
               'before': c['_raw'], 'after': text, 'summary': summary, 'by': by, 'at': H.now()}
    atomic_write(ROOT / '.state/move.json', json.dumps(journal, ensure_ascii=False))
    _recover_move()
    parsed = parse(dest)
    c.clear()
    c.update(parsed)
    return dest


def confirm(c, by="cli"):
    c["confirmed"] = TODAY.isoformat()
    save(c, "confirmed still true", by)


def retire(c, reason="", by="cli"):
    if c["_folder"] == "retired":
        return c["_path"]
    c["retired"] = TODAY.isoformat()
    c["retired_reason"] = reason
    return _move(c, "retired", "retired" + (f": {reason}" if reason else ""), by)


def unretire(c, by="cli"):
    if c["_folder"] != "retired":
        return None
    for k in ("retired", "retired_reason"):
        c.pop(k, None)
    return _move(c, "inbox", "brought back from retired, as a draft", by)


def set_personal(c, want=True, by="cli"):
    if c["_personal"] == want:
        return None
    return _move(c, c["_folder"], "made personal: this Mac only, out of git" if want else
                 "shared: goes to git with the other cards", by, personal=want)


def lint():
    cards, problems = load(), []
    ids = {c.get("id") for c in cards} | {c["_slug"] for c in cards}
    seen = {}
    for c in cards:
        where = c["_path"].relative_to(ROOT)
        if not re.fullmatch(r"a-[0-9a-f]{6}", c.get("id", "")):
            problems.append(f"{where}: id must look like a-1b2c3d")
        if c.get("id") in seen:
            problems.append(f"{where}: id {c['id']} also used by {seen[c['id']]}")
        seen[c.get("id")] = where
        if c["_folder"] == "cards":
            problems += [f"{where}: missing {k}" for k in REQUIRED if not c.get(k)]
        if c.get("host") and c["host"] not in CFG["hosts"]:
            problems.append(f"{where}: host {c['host']!r} is not in atlas.json")
        problems += [f"{where}: link {l!r} matches no card" for l in c.get("links", []) if l not in ids]
    return cards, problems


def short_version(c):
    m = re.search(r"## Short version\n(.*?)(?=\n## |\Z)", c["_body"], re.S)
    text = " ".join(m.group(1).split()) if m else ""
    text = text.replace("**", "").replace("`", "")
    return "" if text.startswith("Two or three lines") else text


def ago(iso):
    try:
        mins = int((dt.datetime.now() - dt.datetime.fromisoformat(iso)).total_seconds() // 60)
    except (TypeError, ValueError):
        return "never"
    return f"{mins} min ago" if mins < 90 else f"{mins // 60} h ago" if mins < 48 * 60 else f"{mins // 1440} days ago"


def last_checked(st):
    return max((v["at"] for v in st.values()), default=None)


def fresh(st, hours=6):
    last = last_checked(st)
    return bool(last) and (dt.datetime.now() - dt.datetime.fromisoformat(last)).total_seconds() < hours * 3600


def clip(text, n):
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def rebuild(cards=None, st=None):
    cards = cards if cards is not None else load()
    st = st if st is not None else state()
    build_md(cards, st)
    return build_html(cards, st)
