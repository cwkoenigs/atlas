"""What every wiki page is built from: a fresh read of the cards, the link graph, and markdown with wiki links.

Links, three kinds, all computed from the cards (nothing to maintain by hand):
  [[Page title]] or [[Page title|shown text]] in any card links to that page (a missing page links to
  "create it"); a card's `links:` field; and a path in `code` (`~/Developer/x`) links to the page about
  that folder. Folders also nest: a card whose folder is inside another card's folder is part of it.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import subprocess
import urllib.parse

from markdown_it import MarkdownIt

from .. import core as A
from .. import history as H

def e(s) -> str:
    """HTML-escape anything, None as empty."""
    return html.escape("" if s is None else str(s))


MD = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False}).enable(["table", "strikethrough"])
KINDS = ["site", "app", "service", "job", "repo", "folder", "domain", "device"]
TOKEN = ""                       # set by the server at start; every form carries it

CODE_SPLIT = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`)")
WIKILINK = re.compile(r"\[\[([^\[\]|\n]+?)(?:\|([^\[\]\n]+?))?\]\]")
BARE_URL = re.compile(r"(?<![<(\[\w/\"'=])(https?://[^\s<>()\[\]`\"']+[^\s<>()\[\]`\"'.,;:!?])")
BARE_GH = re.compile(r"(?<![\w/.:@-])github\.com/([\w.-]+)/([\w-]+(?:\.[\w-]+)*)")
REPO = re.compile(r"github\.com[:/]([\w.-]+/[\w-]+)|GitHub\s+([\w.-]+/[\w-]+)", re.I)
PATHISH = re.compile(r"(?:~|/Users/[^/\s]+)(?:/[^\s`'\"()<>,;|\]\[]+)+")
SECRET = re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}|\bsk-[A-Za-z0-9_-]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}"
                    r"|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
                    r"|(?i:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=]{16,}")


def q(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def page_url(c) -> str:
    return f"/wiki/{q(c['_slug'])}"


def anchor(text: str, used: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"
    a, n = base, 2
    while a in used:
        a, n = f"{base}-{n}", n + 1
    used.add(a)
    return a


def when(iso: str) -> str:
    """2026-10-24 10:15 -> 'today 10:15', 'yesterday 09:00', 'Mon 10/19 14:02', '2026-09-01'."""
    try:
        t = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    days = (dt.date.today() - t.date()).days
    if days == 0:
        return f"today {t:%H:%M}"
    if days == 1:
        return f"yesterday {t:%H:%M}"
    if days < 7:
        return f"{t:%a %m/%d %H:%M}"
    return f"{t:%Y-%m-%d}"


def norm_path(text: str) -> str:
    return os.path.normpath(os.path.expanduser(text.strip().rstrip("/")))


def primary_path(c) -> str:
    """The folder a card is about: its `where`, when that starts with a path (spaces allowed)."""
    w = (c.get("where") or "").strip()
    if not w.startswith(("~/", "/")):
        return ""
    w = re.split(r" \(|, | · ", w, maxsplit=1)[0]
    p = norm_path(w)
    home = os.path.expanduser("~")
    if p in (home, f"{home}/Developer", f"{home}/Documents", f"{home}/code") or p.count("/") < 3:
        return ""
    return p


def source_path(c) -> str:
    s = (c.get("source") or "").strip()
    return norm_path(re.split(r" \(|, | · ", s, maxsplit=1)[0]) if s.startswith(("~/", "/")) else ""


def repo_of(c) -> str:
    for key in ("source", "where"):
        m = REPO.search(c.get(key) or "")
        if m:
            return (m.group(1) or m.group(2)).lower().removesuffix(".git")
    return ""


def plain(text: str) -> str:
    return re.sub(r"[#*`>|_]+", "", text or "")


class Snap:
    """Everything one request needs, read fresh: the cards, check results, and how pages connect."""

    def __init__(self):
        A.CFG = json.loads((A.ROOT / "atlas.json").read_text())
        A.TODAY = dt.date.today()
        self.cards = A.load()
        H.sync(A.ROOT, self.cards)
        self.st = A.state()
        self.notice = ""
        self.hosts = A.CFG["hosts"]
        self.active = [c for c in self.cards if c["_folder"] != "retired"]
        self.by_slug = {c["_slug"]: c for c in self.cards}
        self.by_key = {}
        for c in sorted(self.cards, key=lambda c: c["_folder"] != "retired"):   # live pages win a name
            keys = [c["_slug"], c.get("id", ""), c["title"]] + list(c.get("aliases") or [])
            for k in keys:
                if k:
                    self.by_key[k.lower()] = c
        folders = [(primary_path(c), c) for c in self.cards]
        self.folders = sorted([(p, c) for p, c in folders if p],
                              key=lambda x: (-len(x[0]), x[1]["_folder"] == "retired"))
        self._graph = None

    # names
    def kinds(self) -> list[str]:
        found = {c.get("kind", "") for c in self.active if c.get("kind")}
        return [k for k in KINDS if k in found] + sorted(found - set(KINDS))

    def host_name(self, h: str) -> str:
        return self.hosts.get(h, h or "nowhere yet")

    def resolve(self, target: str):
        """[[target]] -> (url, label, exists)."""
        t = target.strip()
        if "/" in t and not t.startswith(("~", "/")):
            t = t.rsplit("/", 1)[-1]                       # [[cards/slug|Title]], as ATLAS.md writes them
        c = self.by_key.get(t.lower())
        if c:
            return page_url(c), c["title"], True
        for k, name in self.hosts.items():
            if t.lower() in (k.lower(), name.lower()):
                return f"/host/{q(k)}", name, True
        if t.lower() in self.kinds():
            return f"/kind/{q(t.lower())}", t, True
        return f"/special/new?title={q(t)}", t, False

    def card_for_path(self, text: str):
        """The page about the most specific folder containing this path."""
        if not text.startswith(("~/", "/")):
            return None
        p = norm_path(text)
        for folder, c in self.folders:
            if p == folder or p.startswith(folder + "/"):
                return c
        return None

    def parent(self, c):
        """The card whose folder this card's folder (or, for a deployed thing, its source) sits inside."""
        own = primary_path(c)
        for path in (own, source_path(c)):
            if not path:
                continue
            for folder, d in self.folders:
                if d is c or d["_folder"] == "retired":
                    continue
                if path.startswith(folder + "/") or (path == folder and not own):
                    return d
        return None

    # the graph
    def graph(self):
        """(outgoing, incoming): slug -> {other slug: why}."""
        if self._graph:
            return self._graph
        out = {c["_slug"]: {} for c in self.cards}
        for c in self.cards:
            mine = out[c["_slug"]]
            for l in c.get("links") or []:
                t = self.by_key.get(str(l).lower())
                if t and t is not c:
                    mine.setdefault(t["_slug"], "listed as related")
            text = full_text(c)
            for m in WIKILINK.finditer(text):
                url, _, ok = self.resolve(m.group(1))
                t = self.by_key.get(m.group(1).strip().rsplit("/", 1)[-1].lower()) if ok else None
                if t and t is not c:
                    mine.setdefault(t["_slug"], "links to it")
            spans = re.findall(r"`([^`\n]+)`", text) + PATHISH.findall(text)
            for path in spans:
                t = self.card_for_path(path.strip())
                if t and t is not c:
                    mine.setdefault(t["_slug"], "mentions its folder")
        inc = {c["_slug"]: {} for c in self.cards}
        for s, targets in out.items():
            for t, why in targets.items():
                inc.setdefault(t, {})[s] = why
        self._graph = (out, inc)
        return self._graph

    def wanted(self):
        """Missing pages: [[targets]] that resolve to nothing, with the pages that want them."""
        want = {}
        for c in self.cards:
            for m in WIKILINK.finditer(full_text(c)):
                _, label, ok = self.resolve(m.group(1))
                if not ok:
                    want.setdefault(m.group(1).strip(), []).append(c)
        return want


def full_text(c) -> str:
    return "\n".join(str(c.get(k) or "") for k in ("where", "what", "why", "source", "entry")) + "\n" + c.get("_body", "")


# ── markdown with wiki links ─────────────────────────────────────────────────

def _md_label(s: str) -> str:
    return re.sub(r"([\\\[\]*_`<>])", r"\\\1", s)


def _wikify(snap: Snap, s: str) -> str:
    def link(m):
        url, label, ok = snap.resolve(m.group(1))
        return f"[{_md_label((m.group(2) or (label if ok else m.group(1))).strip())}]({url})"
    s = WIKILINK.sub(link, s)
    s = BARE_URL.sub(r"<\1>", s)
    s = BARE_GH.sub(lambda m: f"[github.com/{m.group(1)}/{m.group(2)}](https://github.com/{m.group(1)}/{m.group(2)})", s)
    return s


def _outside_code(text: str, fn) -> str:
    parts = CODE_SPLIT.split(text)
    return "".join(p if i % 2 else fn(p) for i, p in enumerate(parts))


def _post(snap: Snap, h: str, me=None) -> str:
    h = h.replace('<a href="/special/new?', '<a class="new" title="No page yet: follow it to create one" href="/special/new?')
    h = re.sub(r'<a href="(https?://)', r'<a class="ext" rel="noopener noreferrer" href="\1', h)
    out, last = [], 0
    for m in re.finditer(r"<code>([^<]{2,300})</code>", h):
        if h[max(0, m.start() - 5):m.start()] == "<pre>":
            continue
        before = h[:m.start()]
        if before.rfind("<a ") > before.rfind("</a>"):
            continue
        c = snap.card_for_path(html.unescape(m.group(1)))
        if not c or c is me:
            continue
        out += [h[last:m.start()], f'<a class="page-link" href="{page_url(c)}" title="{e(c["title"])}">{m.group(0)}</a>']
        last = m.end()
    out.append(h[last:])
    return "".join(out)


def md(snap: Snap, text: str, me=None) -> str:
    return _post(snap, MD.render(_outside_code(text or "", lambda s: _wikify(snap, s))), me)


def md_inline(snap: Snap, text: str, me=None) -> str:
    return _post(snap, MD.renderInline(_outside_code(text or "", lambda s: _wikify(snap, s))), me)


# ── sections of a card body ──────────────────────────────────────────────────

def split_sections(body: str) -> list[str]:
    """parts[0] is the text before the first `## ` heading; every later part starts with its heading.
    "\\n".join(parts) gives the body back exactly."""
    parts, cur, fence = [], [], False
    for line in body.split("\n"):
        if line.startswith(("```", "~~~")):
            fence = not fence
        if not fence and re.match(r"## (?!#)", line):
            parts.append("\n".join(cur))
            cur = [line]
        else:
            cur.append(line)
    parts.append("\n".join(cur))
    return parts


def join_section(parts: list[str], i: int, new: str) -> str:
    new = new.replace("\r\n", "\n").rstrip("\n")
    parts = list(parts)
    parts[i] = new + "\n" if i < len(parts) - 1 or new else new
    return "\n".join(parts)


_PLACEHOLDERS = None


def placeholders() -> dict:
    """Section heading -> the template's hint text, so an untouched section reads as empty."""
    global _PLACEHOLDERS
    if _PLACEHOLDERS is None:
        _PLACEHOLDERS = {}
        tpl = A.ROOT / "templates" / "card.md"
        if tpl.is_file():
            for part in split_sections(A.parse(tpl)["_body"])[1:]:
                head, _, rest = part.partition("\n")
                _PLACEHOLDERS[head[3:].strip()] = " ".join(rest.split())
    return _PLACEHOLDERS


def is_empty(head: str, content: str) -> bool:
    text = " ".join(content.split())
    return not text or text == placeholders().get(head, "\0")


# ── history across the local store and git ───────────────────────────────────

def git_log(paths: list[str]) -> list[dict]:
    """Commits touching these repo-relative paths, newest first, with the path each had then."""
    if not paths or not (A.ROOT / ".git").exists():
        return []
    r = subprocess.run(["git", "-C", str(A.ROOT), "log", "--follow" if len(paths) == 1 else "--no-renames",
                        "--name-only", "--format=@@%H%x09%cI%x09%s", "--", *paths],
                       capture_output=True, text=True, timeout=10)
    out, cur = [], None
    for line in r.stdout.splitlines():
        if line.startswith("@@"):
            sha, at, subject = (line[2:].split("\t", 2) + ["", ""])[:3]
            local = dt.datetime.fromisoformat(at).astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
            cur = {"sha": sha, "at": local, "summary": subject, "by": "git", "paths": []}
            out.append(cur)
        elif line.strip() and cur is not None:
            cur["paths"].append(line.strip())
    return out


def revisions(c) -> list[dict]:
    """Every known version of a card, newest first: local history (h<n>) and, for shared cards, git (g<sha>)."""
    revs = [{**x, "key": f"h{x['n']}"} for x in H.entries(A.ROOT, c.get("id"))]
    if not c["_personal"]:
        rel = str(c["_path"].relative_to(A.ROOT))
        for g in git_log([rel]):
            path = g["paths"][0] if g["paths"] else rel
            revs.append({"key": f"g{g['sha'][:12]}", "sha": g["sha"], "path": path, "at": g["at"],
                         "by": "git", "summary": g["summary"]})
    revs.sort(key=lambda r: (r["at"], r.get("n", 0)), reverse=True)   # same second: the later save first
    return revs


def revision_text(rev: dict) -> str:
    if "text" in rev:
        return rev["text"]
    r = subprocess.run(["git", "-C", str(A.ROOT), "show", f"{rev['sha']}:{rev['path']}"],
                       capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else ""


def parse_text(text: str, like) -> dict:
    """A card dict from a version's text, placed like the current card (for rendering an old version)."""
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    c = dict(like)
    if not m:
        c["_body"] = text
        return c
    for k in list(c):
        if not k.startswith("_"):
            c.pop(k)
    tmp = A.ROOT / ".state" / "rev.md"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text(text)
    parsed = A.parse(tmp)
    tmp.unlink()
    for k, v in parsed.items():
        if not k.startswith("_") or k == "_body":
            c[k] = v
    return c
