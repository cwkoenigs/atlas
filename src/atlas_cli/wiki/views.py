"""The wiki's pages. Each view takes a fresh Snap and returns (title, main html, menu key, search text)."""
from __future__ import annotations

import datetime as dt
import difflib
import pathlib
import re

from .. import core as A
from .. import history as H
from . import render as R
from .render import Snap, e, page_url, q

SHELL = pathlib.Path(__file__).with_name("shell.html").read_text()
LABELS = [("where", "Where"), ("what", "What"), ("why", "Why"), ("source", "Edit it at"), ("entry", "Get to it")]
HELP = {
    "title": "What you call it. Other pages link to it by this name.",
    "where": "The exact place: a path, a project, a URL.",
    "what": "One line: what it does.",
    "why": "One line: why it exists and who needs it. Leave it empty if nobody knows yet.",
    "source": "Where you change it: the repo and the path in it.",
    "entry": "How to get to it: a URL or a command.",
    "check": "A command that succeeds only while this page is true: read-only, run from your home folder, under 15 seconds.",
    "links": "Related pages by name, separated by commas. In the text, [[Page name]] links too.",
}
CONFIDENCE = [("confirmed", "Confirmed: seen to be true"), ("believed", "Believed: very likely true"), ("guess", "Guess: not checked yet")]
SPECIAL = [("Needs a look", "/special/attention", "failing checks, drafts, guesses, stale pages"),
           ("Recent changes", "/special/recent", "every edit, newest first"),
           ("All pages", "/special/all", "A to Z"),
           ("Places", "/special/places", "where things run"),
           ("Kinds", "/special/kinds", "sites, repos, jobs and the rest"),
           ("Wanted pages", "/special/wanted", "links to pages nobody has written"),
           ("Retired pages", "/special/retired", "things that are gone, kept for their history"),
           ("Random page", "/special/random", "any page"),
           ("New page", "/special/new", "start a page")]


def kind_label(k: str) -> str:
    k = k or "unsorted"
    return k[:1].upper() + k[1:] + ("" if k.endswith("s") else "s")


def token_input() -> str:
    return f'<input type="hidden" name="token" value="{e(R.TOKEN)}">'


def chip(snap: Snap, c) -> str:
    word, s = A.status(c, snap.st)
    return f'<span class="chip" data-state="{e(s)}">{e(word)}</span>'


def chips(snap: Snap, c) -> str:
    out = [chip(snap, c)]
    if c["_personal"]:
        out.append('<span class="chip" data-state="personal" title="Kept on this Mac only, never in git">Personal</span>')
    if c.get("confidence") == "guess" and c["_folder"] != "retired":
        out.append('<span class="chip" data-state="guess">Guess</span>')
    return '<span class="chips">' + "".join(out) + "</span>"


def link(c, text=None) -> str:
    return f'<a href="{page_url(c)}">{e(text or c["title"])}</a>'


def rows(snap: Snap, cards, detail=lambda c: c.get("what", "")) -> str:
    if not cards:
        return '<p class="empty">None.</p>'
    items = "".join(f'<li>{link(c)}{chips(snap, c)}<span class="sub">{R.md_inline(snap, detail(c), c)}</span></li>' for c in cards)
    return f'<ul class="rows">{items}</ul>'


# ── the frame around every page ──────────────────────────────────────────────

def document(snap: Snap, title: str, main: str, active: str = "", query: str = "", nonce: str = "") -> str:
    vals = {"title": e("Atlas" if title == "Atlas" else f"{title} · Atlas"), "nonce": nonce, "query": e(query),
            "barlinks": barlinks(active), "sidebar": sidebar(snap, active), "main": main, "footer": footer(snap)}
    return re.sub(r"\{\{(\w+)\}\}", lambda m: vals.get(m.group(1), ""), SHELL)


def _cur(active, key):
    return ' aria-current="page"' if active == key else ""


def barlinks(active: str) -> str:
    return (f'<a href="/special/recent"{_cur(active, "recent")}>Recent changes</a>'
            f'<a href="/special/new"{_cur(active, "new")}>New page</a>')


def sidebar(snap: Snap, active: str) -> str:
    att = A.attention(snap.active, snap.st)

    def item(key, url, label, count: object = ""):
        n = f'<span class="count">{count}</span>' if count != "" else ""
        return f'<li><a href="{url}"{_cur(active, key)}><span>{e(label)}</span>{n}</a></li>'
    nav = "".join([item("main", "/", "Main page"), item("attention", "/special/attention", "Needs a look", len(att)),
                   item("recent", "/special/recent", "Recent changes"), item("all", "/special/all", "All pages", len(snap.active)),
                   item("random", "/special/random", "Random page"), item("special", "/special", "Special pages")])
    hosts = {}
    for c in snap.active:
        hosts[c.get("host", "")] = hosts.get(c.get("host", ""), 0) + 1
    order = list(snap.hosts) + sorted(h for h in hosts if h not in snap.hosts)
    places = "".join(item(f"host:{h}", f"/host/{q(h)}", snap.host_name(h), hosts.get(h, 0)) for h in order)
    kinds = "".join(item(f"kind:{k}", f"/kind/{q(k)}", kind_label(k), sum(1 for c in snap.active if c.get("kind") == k))
                    for k in snap.kinds())
    return (f"<h2>Atlas</h2><ul>{nav}</ul>"
            f'<div class="more"><h2>Places</h2><ul>{places}</ul><h2>Kinds</h2><ul>{kinds}</ul></div>')


def footer(snap: Snap) -> str:
    return (f"<span>Atlas · what runs where, and why · {len(snap.active)} pages, each a markdown card in the atlas repo</span>"
            "<span><kbd>/</kbd> search · <kbd>e</kbd> edit · personal pages never leave this Mac</span>")


def notice(snap: Snap) -> str:
    return snap.notice or ""


# ── article ──────────────────────────────────────────────────────────────────

def head(snap: Snap, c, tab: str, title: str | None = None) -> str:
    url = page_url(c)
    out, inc = snap.graph()
    n_links = len(set(out.get(c["_slug"], {})) | set(inc.get(c["_slug"], {})))
    n_hist = len(R.revisions(c)) if tab == "history" else None
    tabs = [("read", url, "Read", ""), ("edit", f"{url}/edit", "Edit", ""),
            ("history", f"{url}/history", "History", n_hist if n_hist is not None else ""),
            ("links", f"{url}/links", "Links", n_links)]
    tab_html = "".join(f'<a href="{u}"{_cur(tab, k)}{" data-key=edit" if k == "edit" else ""}>{lbl}'
                       + (f'<span class="n">{n}</span>' if n != "" else "") + "</a>" for k, u, lbl, n in tabs)
    host, kind = c.get("host", ""), c.get("kind", "")
    return (f'<p class="crumbs"><a href="/host/{q(host)}">{e(snap.host_name(host))}</a> › '
            f'<a href="/kind/{q(kind)}">{e(kind_label(kind))}</a></p>'
            f'<div class="titlebar"><h1>{e(title or c["title"])}</h1>{chips(snap, c)}</div>'
            f'<nav class="tabs" aria-label="This page">{tab_html}</nav>{notice(snap)}')


def body_html(snap: Snap, c, editable=True):
    """(html, contents) for a card's text: its ## sections, each with an edit link; empty ones say so."""
    parts = R.split_sections(c.get("_body", ""))
    used, toc, out = set(), [], []
    if parts[0].strip():
        out.append(R.md(snap, parts[0], c))
    for i, part in enumerate(parts[1:], 1):
        line, _, content = part.partition("\n")
        text = line[3:].strip()
        aid = R.anchor(text, used)
        toc.append((aid, text))
        edit = f'<a class="edit-section" href="{page_url(c)}/edit?section={i}">edit</a>' if editable else ""
        out.append(f'<h2 id="{aid}">{R.md_inline(snap, text, c)}{edit}</h2>')
        if R.is_empty(text, content):
            add = f' <a href="{page_url(c)}/edit?section={i}">Add it</a>.' if editable else ""
            out.append(f'<p class="empty">Nothing here yet.{add}</p>')
        else:
            out.append(R.md(snap, content, c))
    return "\n".join(out), toc


def infobox(snap: Snap, c, actions=True) -> str:
    url = page_url(c)
    word, s = A.status(c, snap.st)
    res = snap.st.get(c.get("id"))
    status = f'<span class="chip" data-state="{e(s)}">{e(word)}</span>'
    if res and c["_folder"] != "retired":
        status += f' <span class="sub">checked {e(A.ago(res["at"]))}</span>'
        if not res["ok"]:
            status += f'<span class="checkout"><code>{e(res["out"] or "failed, with no output")}</code></span>'
    trs = [("Status", status),
           ("Place", f'<a href="/host/{q(c.get("host", ""))}">{e(snap.host_name(c.get("host", "")))}</a>'),
           ("Kind", f'<a href="/kind/{q(c.get("kind", ""))}">{e(c.get("kind") or "unsorted")}</a>')]
    for key, label in LABELS:
        v = str(c.get(key) or "").strip()
        trs.append((label, R.md_inline(snap, v, c) if v else
                    (f'<a class="missing" href="{url}/edit#f-{key}">Not written yet: add it</a>' if actions else '<span class="empty">Not written</span>')))
    check = str(c.get("check") or "").strip()
    trs.append(("Check", f"<code>{e(check)}</code>" if check else
                (f'<a class="missing" href="{url}/edit#f-check">No check yet: add one</a>' if actions else '<span class="empty">None</span>')))
    conf = c.get("confidence") or "not set"
    confirmed = c.get("confirmed")
    stale = c["_folder"] == "cards" and A.stale(c)
    trs.append(("Confidence", e(conf) + (f' <span class="sub">· confirmed {e(confirmed)}{", a while ago" if stale else ""}</span>'
                                          if confirmed else ' <span class="sub">· never confirmed</span>')))
    trs.append(("Kept", "Personal: this Mac only, never in git" if c["_personal"] else "Shared: in the atlas repo on GitHub"))
    trs.append(("Terminal", f'<code>atlas {e(c["_slug"])}</code>'))
    table = "".join(f"<tr><th>{e(k)}</th><td>{v}</td></tr>" for k, v in trs)
    act = ""
    if actions:
        b = ['<button class="btn" name="action" value="check">Run check</button>']
        if c["_folder"] == "inbox":
            b.insert(0, '<button class="btn primary" name="action" value="promote">Promote to the map</button>')
        elif c["_folder"] == "cards":
            b.append('<button class="btn" name="action" value="confirm">Still true</button>')
        if c["_folder"] == "retired":
            b = ['<button class="btn primary" name="action" value="unretire">Bring it back</button>']
        else:
            b.append('<button class="btn" name="action" value="share">Share it in git</button>' if c["_personal"] else
                     '<button class="btn" name="action" value="personal">Make it personal</button>')
            b.append('<details><summary class="btn">Retire…</summary>'
                     '<input type="text" name="reason" placeholder="Why it is gone" aria-label="Why it is gone">'
                     '<button class="btn" name="action" value="retire">Retire it</button></details>')
        act = f'<form class="actions" method="post" action="{url}/do">{token_input()}{"".join(b)}</form>'
    return f'<section class="infobox" aria-label="At a glance"><h2>At a glance</h2><table>{table}</table>{act}</section>'


def connections(snap: Snap, c, full=False) -> str:
    out, inc = snap.graph()
    slug = c["_slug"]

    def names(pairs):
        return " · ".join(link(d) + (f' <span class="why">({e(why)})</span>' if full and why else "") for d, why in pairs)
    groups = []
    parent = snap.parent(c)
    if parent:
        groups.append(("Part of", names([(parent, "")])))
    kids = sorted((d for d in snap.active if d is not c and snap.parent(d) is c), key=lambda d: d["title"].lower())
    if kids:
        groups.append(("Inside it", names([(d, "") for d in kids])))
    to = [(snap.by_slug[s], why) for s, why in out.get(slug, {}).items() if s in snap.by_slug]
    here = [(snap.by_slug[s], why) for s, why in inc.get(slug, {}).items() if s in snap.by_slug]
    if to:
        groups.append(("Links to", names(sorted(to, key=lambda x: x[0]["title"].lower()))))
    if here:
        groups.append(("Links here", names(sorted(here, key=lambda x: x[0]["title"].lower()))))
    repo = R.repo_of(c)
    same = sorted((d for d in snap.cards if d is not c and repo and R.repo_of(d) == repo), key=lambda d: d["title"].lower())
    if same:
        groups.append(("Same repo", names([(d, "") for d in same]) + f' <span class="why">github.com/{e(repo)}</span>'))
    if full:
        peers = [d for d in snap.active if d is not c and d.get("host") == c.get("host")]
        groups.append(("Same place", f'<a href="/host/{q(c.get("host", ""))}">{e(snap.host_name(c.get("host", "")))}</a>'
                                     f' <span class="why">{len(peers)} other pages</span>'))
    if not groups:
        return (f'<p class="empty">Nothing links here yet. Write <code>[[{e(c["title"])}]]</code> in another page '
                f'to link it, or add it to that page\'s related pages.</p>')
    return '<dl class="connections">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in groups) + "</dl>"


def lastmod(c) -> str:
    revs = R.revisions(c)
    if not revs:
        return ""
    r = revs[0]
    how = H.BY.get(r["by"], r["by"]) + (f': {r["summary"]}' if r.get("summary") else "")
    return (f'<p class="lastmod sub">Last changed {e(R.when(r["at"]))} ({e(how)}) · '
            f'<a href="{page_url(c)}/history">History</a></p>')


def article(snap: Snap, c):
    body, toc = body_html(snap, c)
    url = page_url(c)
    banner = ""
    if c["_folder"] == "retired":
        banner = (f'<div class="banner-retired">Retired {e(c.get("retired", ""))}'
                  f'{": " + e(c.get("retired_reason")) if c.get("retired_reason") else ""}. '
                  'It stays here so its history does; bring it back if it returns.</div>')
    elif c["_folder"] == "inbox":
        banner = ('<div class="banner-retired">A draft: not on the map yet. Check the facts, write why it exists, '
                  'then promote it.</div>')
    lead = f'<p class="lead">{R.md_inline(snap, c.get("what", ""), c)}</p>' if c.get("what") else ""
    toc_html = ""
    if len(toc) >= 2:
        toc_html = ('<nav class="toc" aria-label="On this page"><h2>On this page</h2>'
                    + "".join(f'<a href="#{a}">{e(t)}</a>' for a, t in toc)
                    + '<a href="#connections">Connections</a></nav>')
    main = (head(snap, c, "read") + banner +
            f'<div class="article"><div class="prose">{lead}{body}'
            f'<h2 id="connections">Connections</h2>{connections(snap, c)}{lastmod(c)}</div>'
            f'<aside class="rail">{infobox(snap, c)}{toc_html}</aside></div>')
    return c["title"], main, f"page:{c['_slug']}", ""


def links_page(snap: Snap, c):
    main = (head(snap, c, "links") + '<p class="lead">How this page connects to the rest of the atlas: links written in '
            'the pages, related pages, folders inside each other, and code from the same repo.</p>'
            f'<div class="stack">{connections(snap, c, full=True)}</div>')
    return f"Links: {c['title']}", main, f"page:{c['_slug']}", ""


# ── editing ──────────────────────────────────────────────────────────────────

def form_values(snap: Snap, c) -> dict:
    v = {k: str(c.get(k) or "") for k in ("title", "kind", "host", "where", "what", "why", "source", "entry", "check", "confidence")}
    v["links"] = ", ".join((snap.by_key.get(str(l).lower()) or {}).get("title", str(l)) for l in c.get("links") or [])
    v["personal"] = "yes" if c["_personal"] else ""
    v["body"] = c.get("_body", "").lstrip("\n")
    v["summary"] = ""
    return v


def _input(name, value, label, help_=True, mono=False):
    h = f'<p class="help">{e(HELP[name])}</p>' if help_ and name in HELP else ""
    return (f'<label for="f-{name}">{e(label)}</label><div><input type="text" id="f-{name}" name="{name}" '
            f'value="{e(value)}"{" class=mono spellcheck=false" if mono else ""}>{h}</div>')


def _select(name, value, label, options):
    opts = "".join(f'<option value="{e(k)}"{" selected" if k == value else ""}>{e(t)}</option>' for k, t in options)
    return f'<label for="f-{name}">{e(label)}</label><div><select id="f-{name}" name="{name}">{opts}</select></div>'


def edit_form(snap: Snap, v: dict, action: str, cancel: str, section: int | None = None, base: str = "", new=False) -> str:
    fields = ""
    if section is None:
        kinds = R.KINDS + ([v["kind"]] if v["kind"] and v["kind"] not in R.KINDS else [])
        hosts = list(snap.hosts.items()) + ([(v["host"], v["host"])] if v["host"] and v["host"] not in snap.hosts else [])
        fields = ('<div class="form-grid">'
                  + _input("title", v["title"], "Title")
                  + _select("kind", v["kind"] or "service", "Kind", [(k, k) for k in kinds])
                  + _select("host", v["host"] or next(iter(snap.hosts)), "Place", hosts)
                  + _input("where", v["where"], "Where") + _input("what", v["what"], "What")
                  + f'<label for="f-why">Why</label><div><textarea class="short" id="f-why" name="why">{e(v["why"])}</textarea>'
                    f'<p class="help">{e(HELP["why"])}</p></div>'
                  + _input("source", v["source"], "Edit it at") + _input("entry", v["entry"], "Get to it")
                  + _input("check", v["check"], "Check", mono=True) + _input("links", v["links"], "Related pages")
                  + _select("confidence", v["confidence"] or "believed", "Confidence", CONFIDENCE)
                  + '<label for="f-personal">Personal</label><div class="check-row">'
                    f'<input type="checkbox" id="f-personal" name="personal" value="yes"{" checked" if v.get("personal") else ""}>'
                    '<span>Keep it on this Mac only, out of git and off other computers</span></div>'
                  + "</div>")
    sec = f'<input type="hidden" name="section" value="{section}">' if section is not None else ""
    label = "This section" if section is not None else "Page text"
    return (f'<form class="edit" method="post" action="{action}">{token_input()}'
            f'<input type="hidden" name="base" value="{e(base)}">{sec}{fields}'
            f'<h2 id="f-body-label">{label}</h2>'
            '<p class="help">Markdown. <code>[[Page name]]</code> links to another page; a path in backticks, like '
            '<code>`~/Developer/atlas`</code>, links to the page about that folder. Sections start with <code>## </code>.</p>'
            f'<textarea id="f-body" name="body" aria-labelledby="f-body-label" spellcheck="true">{e(v["body"])}</textarea>'
            '<div class="form-grid" style="margin-top:18px"><label for="f-summary">Summary</label><div>'
            f'<input type="text" id="f-summary" name="summary" value="{e(v.get("summary", ""))}" '
            'placeholder="What you changed, in a few words"><p class="help">Shown in the history and in recent changes.</p></div></div>'
            '<div class="buttons">'
            f'<button class="btn primary" name="do" value="save">{"Create the page" if new else "Save"}</button>'
            '<button class="btn" name="do" value="preview">Show preview</button>'
            f'<a href="{cancel}">Cancel</a><span class="sub">Cmd-S saves</span></div></form>')


def edit(snap: Snap, c, v=None, problem="", preview="", section=None, base=""):
    if v is None:
        v = form_values(snap, c)
        if section is not None:
            parts = R.split_sections(c.get("_body", ""))
            v["body"] = parts[section].rstrip("\n") + "\n" if 0 <= section < len(parts) else ""
    title = f"Editing {c['title']}" + (" (a section)" if section is not None else "")
    prob = f'<div class="notice" data-kind="fail"><p>{problem}</p></div>' if problem else ""
    main = (head(snap, c, "edit", title) + prob + preview +
            edit_form(snap, v, f"{page_url(c)}/edit", page_url(c), section, base))
    return title, main, f"page:{c['_slug']}", ""


def new_page(snap: Snap, v=None, problem="", preview=""):
    if v is None:
        v = {k: "" for k in ("title", "kind", "host", "where", "what", "why", "source", "entry", "check", "links", "summary")}
        v.update(personal="yes", confidence="guess", body=A.parse(A.ROOT / "templates" / "card.md")["_body"].lstrip("\n"))
    prob = f'<div class="notice" data-kind="fail"><p>{problem}</p></div>' if problem else ""
    main = ('<p class="crumbs"><a href="/special">Special pages</a></p><div class="titlebar"><h1>New page</h1></div>'
            '<p class="lead">One page per thing that runs somewhere. It starts as a draft; promote it once the facts are checked.</p>'
            + notice(snap) + prob + preview + edit_form(snap, v, "/special/new", "/", None, "", new=True))
    return "New page", main, "new", ""


def preview_block(snap: Snap, c) -> str:
    body, _ = body_html(snap, c, editable=False)
    lead = f'<p class="lead">{R.md_inline(snap, c.get("what", ""), c)}</p>' if c.get("what") else ""
    return (f'<section class="preview" aria-label="Preview"><p class="sub">Preview, not saved yet</p>'
            f'<div class="article"><div class="prose"><h1>{e(c["title"])}</h1>{lead}{body}</div>'
            f'<aside class="rail">{infobox(snap, c, actions=False)}</aside></div></section>')


# ── history ──────────────────────────────────────────────────────────────────

def history(snap: Snap, c):
    revs = R.revisions(c)
    url = page_url(c)
    if not revs:
        return f"History: {c['title']}", head(snap, c, "history") + '<p class="empty">No versions kept yet.</p>', f"page:{c['_slug']}", ""
    trs = []
    for i, r in enumerate(revs):
        older = revs[i + 1]["key"] if i + 1 < len(revs) else None
        diff = f'<a href="{url}/diff?a={older}&amp;b={r["key"]}">changes</a>' if older else '<span class="sub">first</span>'
        cur = ' <span class="chip">current</span>' if i == 0 else ""
        trs.append(f'<tr><td class="radio"><input type="radio" name="a" value="{r["key"]}" aria-label="compare from"{" checked" if i == 1 else ""}></td>'
                   f'<td class="radio"><input type="radio" name="b" value="{r["key"]}" aria-label="compare to"{" checked" if i == 0 else ""}></td>'
                   f'<td><a href="{url}/rev/{r["key"]}">{e(R.when(r["at"]))}</a>{cur}</td>'
                   f'<td>{e(H.BY.get(r["by"], r["by"]))}</td><td>{e(r.get("summary") or "")}</td><td>{diff}</td></tr>')
    main = (head(snap, c, "history") +
            '<p class="lead">Every version of this page, newest first: edits here, atlas commands, and changes made in '
            'an editor' + ("" if c["_personal"] else ", plus its commits in git") + '.</p>'
            f'<form class="compare" method="get" action="{url}/diff"><table class="history">'
            '<tr><th>From</th><th>To</th><th>When</th><th>How</th><th>Summary</th><th></th></tr>'
            + "".join(trs) + '</table><div class="buttons"><button class="btn">Compare the two</button></div></form>')
    return f"History: {c['title']}", main, f"page:{c['_slug']}", ""


def find_rev(c, key):
    for r in R.revisions(c):
        if r["key"] == key:
            return r
    return None


def revision(snap: Snap, c, key):
    r = find_rev(c, key)
    if not r:
        return None
    old = R.parse_text(R.revision_text(r), c)
    body, _ = body_html(snap, old, editable=False)
    url = page_url(c)
    bar = (f'<div class="notice"><p>An old version, from {e(R.when(r["at"]))} ({e(H.BY.get(r["by"], r["by"]))}'
           f'{": " + e(r["summary"]) if r.get("summary") else ""}).</p>'
           f'<p><a href="{url}">The current version</a> · <a href="{url}/diff?a={r["key"]}&amp;b=current">What changed since</a></p>'
           f'<form method="post" action="{url}/restore">{token_input()}<input type="hidden" name="key" value="{r["key"]}">'
           '<button class="btn">Restore this version</button></form></div>')
    lead = f'<p class="lead">{R.md_inline(snap, old.get("what", ""), c)}</p>' if old.get("what") else ""
    main = (head(snap, c, "history") + bar +
            f'<div class="article"><div class="prose">{lead}{body}</div><aside class="rail">{infobox(snap, old, actions=False)}</aside></div>')
    return f"{c['title']} (old version)", main, f"page:{c['_slug']}", ""


def diff_rows(a: str, b: str) -> str:
    al, bl = a.splitlines(), b.splitlines()
    out = []
    for group in difflib.SequenceMatcher(None, al, bl, autojunk=False).get_grouped_opcodes(3):
        f, l = group[0], group[-1]
        out.append(f'<tr class="hunk"><td class="gut"></td><td>lines {f[1] + 1} to {l[2]} before, {f[3] + 1} to {l[4]} after</td></tr>')
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                out += [f'<tr><td class="gut"></td><td>{e(x) or " "}</td></tr>' for x in al[i1:i2]]
                continue
            out += [f'<tr class="del"><td class="gut" aria-label="removed">−</td><td>{e(x) or " "}</td></tr>' for x in al[i1:i2]]
            out += [f'<tr class="add"><td class="gut" aria-label="added">+</td><td>{e(x) or " "}</td></tr>' for x in bl[j1:j2]]
    return "".join(out)


def diff(snap: Snap, c, a_key, b_key):
    revs = R.revisions(c)
    by = {r["key"]: r for r in revs}
    current = {"key": "current", "at": revs[0]["at"] if revs else "", "by": "", "summary": "the current version",
               "text": c["_path"].read_text()}
    ra, rb = by.get(a_key) or (current if a_key == "current" else None), by.get(b_key) or (current if b_key in (None, "", "current") else None)
    if not ra or not rb:
        return None
    if ra is not current and rb is not current and ra["at"] > rb["at"]:
        ra, rb = rb, ra
    rows_html = diff_rows(R.revision_text(ra), R.revision_text(rb))
    url = page_url(c)
    name = lambda r: "the current version" if r is current else f'{R.when(r["at"])} ({H.BY.get(r["by"], r["by"])})'
    restore = (f'<form method="post" action="{url}/restore">{token_input()}<input type="hidden" name="key" value="{ra["key"]}">'
               '<button class="btn">Restore the older version</button></form>') if ra is not current else ""
    main = (head(snap, c, "history") +
            f'<p class="lead">Changes from {e(name(ra))} to {e(name(rb))}.</p>' +
            (f'<table class="diff">{rows_html}</table>' if rows_html else '<p class="empty">No differences.</p>') +
            f'<div class="buttons"><a href="{url}/history">Back to the history</a>{restore}</div>')
    return f"Changes: {c['title']}", main, f"page:{c['_slug']}", ""


# ── lists and special pages ──────────────────────────────────────────────────

def events(snap: Snap, limit=200):
    """Every recorded change, newest first: (at, card, by, summary, key, older key)."""
    out = []
    for c in snap.cards:
        hist = H.entries(A.ROOT, c.get("id"))
        for x in hist:
            out.append((x["at"], c, x["by"], x.get("summary", ""), f"h{x['n']}", f"h{x['n'] - 1}" if x["n"] > 1 else None))
    shared = {str(c["_path"].relative_to(A.ROOT)): c for c in snap.cards if not c["_personal"]}
    by_stem = {c["_slug"]: c for c in snap.cards if not c["_personal"]}
    for g in R.git_log(["cards", "inbox", "retired"]):
        for p in g["paths"]:
            c = shared.get(p) or by_stem.get(pathlib.Path(p).stem)
            if c and p.endswith(".md") and "/personal/" not in p:
                out.append((g["at"], c, "git", g["summary"], f"g{g['sha'][:12]}", None))
    out.sort(key=lambda x: (x[0], int(x[4][1:]) if x[4].startswith("h") else 0), reverse=True)
    return out[:limit]


def recent(snap: Snap):
    days, html_days = {}, []
    for ev in events(snap):
        days.setdefault(ev[0][:10], []).append(ev)
    for day, evs in days.items():
        d = dt.date.fromisoformat(day)
        n = (dt.date.today() - d).days
        label = "Today" if n == 0 else "Yesterday" if n == 1 else f"{d:%A %B} {d.day}" if n < 7 else f"{d:%B} {d.day}, {d.year}"
        items = []
        for at, c, by, summary, key, older in evs:
            ch = f' · <a href="{page_url(c)}/diff?a={older}&amp;b={key}">changes</a>' if older else ""
            items.append(f'<li><span class="time">{at[11:16]}</span><span>{link(c)}</span>'
                         f'<span><span class="sub">{e(H.BY.get(by, by))}</span>{": " + e(summary) if summary else ""}{ch}</span></li>')
        html_days.append(f'<section class="day"><h2>{label}</h2><ul class="changes">{"".join(items)}</ul></section>')
    main = ('<div class="titlebar"><h1>Recent changes</h1></div>'
            '<p class="lead">Every change to every page, newest first: edits here, atlas commands, scans, git commits, '
            'and changes made in an editor.</p>' + notice(snap) + ("".join(html_days) or '<p class="empty">No changes yet.</p>'))
    return "Recent changes", main, "recent", ""


def attention(snap: Snap):
    att = A.attention(snap.active, snap.st)
    items = "".join(f'<li>{link(c)}{chips(snap, c)}<span class="sub">{e(A.clip(why, 160))}</span></li>' for _, c, why in att)
    main = ('<div class="titlebar"><h1>Needs a look</h1></div>'
            f'<p class="lead">Most urgent first: failing checks, drafts waiting, guesses, and pages not confirmed in '
            f'{A.CFG.get("stale_days", 30)} days. Checked {e(A.ago(A.last_checked(snap.st)))}.</p>' + notice(snap) +
            f'<form method="post" action="/special/check-all">{token_input()}'
            '<div class="buttons" style="margin:0 0 24px"><button class="btn primary">Check everything now</button>'
            '<span class="sub">Runs every page\'s check; it can take a minute.</span></div></form>'
            + (f'<ul class="rows">{items}</ul>' if items else '<p class="empty">Nothing needs a look.</p>'))
    return "Needs a look", main, "attention", ""


def all_pages(snap: Snap):
    letters = {}
    for c in sorted(snap.active, key=lambda c: c["title"].lower()):
        k = c["title"][:1].upper()
        letters.setdefault(k if k.isalpha() else "#", []).append(c)
    secs = "".join(f'<section><h2>{e(k)}</h2><ul>'
                   + "".join(f'<li>{link(c)} <span class="sub">{e(snap.host_name(c.get("host", "")))} · {e(c.get("kind", ""))}'
                             f'{" · draft" if c["_folder"] == "inbox" else ""}</span></li>' for c in cs)
                   + "</ul></section>" for k, cs in letters.items())
    retired = sum(1 for c in snap.cards if c["_folder"] == "retired")
    main = ('<div class="titlebar"><h1>All pages</h1></div>'
            f'<p class="lead">{len(snap.active)} pages, A to Z. '
            + (f'<a href="/special/retired">{retired} retired</a> are kept apart.' if retired else "") + '</p>'
            f'<div class="letters">{secs}</div>')
    return "All pages", main, "all", ""


def host_page(snap: Snap, key: str):
    cards = [c for c in snap.active if c.get("host") == key]
    if not cards and key not in snap.hosts:
        return None
    att = [c for _, c, _ in A.attention(cards, snap.st)]
    groups = {}
    for c in sorted(cards, key=lambda c: (c["_folder"] == "inbox", c["title"].lower())):
        groups.setdefault(c.get("kind") or "unsorted", []).append(c)
    secs = "".join(f'<h2>{e(kind_label(k))}</h2>{rows(snap, cs)}' for k, cs in sorted(groups.items()))
    main = ('<p class="crumbs"><a href="/special/places">Places</a></p>'
            f'<div class="titlebar"><h1>{e(snap.host_name(key))}</h1></div>'
            f'<p class="lead">{len(cards)} pages run here or live here. {len(att)} need a look.</p>'
            f'<div class="stack">{secs or "<p class=empty>Nothing here yet.</p>"}</div>')
    return snap.host_name(key), main, f"host:{key}", ""


def kind_page(snap: Snap, kind: str):
    cards = [c for c in snap.active if (c.get("kind") or "unsorted") == kind]
    if not cards:
        return None
    groups = {}
    for c in sorted(cards, key=lambda c: (c["_folder"] == "inbox", c["title"].lower())):
        groups.setdefault(c.get("host", ""), []).append(c)
    order = [h for h in snap.hosts if h in groups] + sorted(h for h in groups if h not in snap.hosts)
    secs = "".join(f'<h2><a href="/host/{q(h)}">{e(snap.host_name(h))}</a></h2>{rows(snap, groups[h])}' for h in order)
    main = ('<p class="crumbs"><a href="/special/kinds">Kinds</a></p>'
            f'<div class="titlebar"><h1>{e(kind_label(kind))}</h1></div>'
            f'<p class="lead">{len(cards)} pages of this kind, by place.</p><div class="stack">{secs}</div>')
    return kind_label(kind), main, f"kind:{kind}", ""


def places(snap: Snap):
    blocks = []
    for h in list(snap.hosts) + sorted({c.get("host", "") for c in snap.active} - set(snap.hosts)):
        cs = sorted((c for c in snap.active if c.get("host") == h), key=lambda c: c["title"].lower())
        more = f" · and {len(cs) - 10} more" if len(cs) > 10 else ""
        blocks.append(f'<section><h3><a href="/host/{q(h)}">{e(snap.host_name(h))}</a><span class="count">{len(cs)}</span></h3>'
                      f'<p>{" · ".join(link(c) for c in cs[:10]) or "<span class=empty>Nothing yet</span>"}{more}</p></section>')
    main = ('<div class="titlebar"><h1>Places</h1></div><p class="lead">Where things run or live. Places are set in '
            '<code>atlas.json</code>.</p>' f'<div class="places">{"".join(blocks)}</div>')
    return "Places", main, "special", ""


def kinds(snap: Snap):
    items = "".join(f'<li><a href="/kind/{q(k)}">{e(kind_label(k))}</a><span class="sub">'
                    f'{sum(1 for c in snap.active if c.get("kind") == k)} pages</span></li>' for k in snap.kinds())
    main = '<div class="titlebar"><h1>Kinds</h1></div>' f'<ul class="rows tight">{items}</ul>'
    return "Kinds", main, "special", ""


def retired(snap: Snap):
    cs = sorted((c for c in snap.cards if c["_folder"] == "retired"), key=lambda c: c.get("retired", ""), reverse=True)
    main = ('<div class="titlebar"><h1>Retired pages</h1></div><p class="lead">Things that are gone. Their pages stay, '
            'with their history; bring one back from its page.</p>'
            + rows(snap, cs, lambda c: f'{c.get("retired", "")}: {c.get("retired_reason") or "no reason given"}'))
    return "Retired pages", main, "special", ""


def wanted(snap: Snap):
    want = snap.wanted()
    items = "".join(f'<li><a class="new" href="/special/new?title={q(t)}">{e(t)}</a><span class="sub">wanted by '
                    f'{" · ".join(link(c) for c in cs)}</span></li>' for t, cs in sorted(want.items(), key=lambda x: x[0].lower()))
    main = ('<div class="titlebar"><h1>Wanted pages</h1></div><p class="lead">Pages that other pages link to with '
            '<code>[[...]]</code> but nobody has written. Follow one to create it.</p>'
            + (f'<ul class="rows tight">{items}</ul>' if items else '<p class="empty">None: every link has a page.</p>'))
    return "Wanted pages", main, "special", ""


def special(snap: Snap):
    items = "".join(f'<li><a href="{u}">{e(t)}</a><span class="sub">{e(d)}</span></li>' for t, u, d in SPECIAL)
    main = ('<div class="titlebar"><h1>Special pages</h1></div><p class="lead">Pages the wiki builds from all the others.</p>'
            f'<ul class="rows tight">{items}</ul>')
    return "Special pages", main, "special", ""


# ── search ───────────────────────────────────────────────────────────────────

def rank(snap: Snap, query: str):
    qn = " ".join(query.lower().split())
    words = qn.split()
    if not words:
        return []
    scored = []
    for c in snap.cards:
        title = c["title"].lower()
        fields = " ".join(str(c.get(k) or "") for k in ("where", "what", "why", "source", "entry", "check", "kind")).lower()
        fields += f" {snap.host_name(c.get('host', '')).lower()} {c['_slug']}"
        body = c.get("_body", "").lower()
        if not all(w in f"{title} {fields} {body}" for w in words):
            continue
        score = (100 if title == qn else 0) + sum(12 for w in words if w in title) + sum(4 for w in words if w in fields) \
            + sum(1 for w in words if w in body) - (8 if c["_folder"] == "retired" else 0)
        scored.append((score, c))
    scored.sort(key=lambda x: (-x[0], x[1]["title"].lower()))
    return [c for _, c in scored]


def snippet(c, words) -> str:
    text = " ".join(R.plain(f"{c.get('what', '')} {c.get('why', '')} {c.get('_body', '')}").split())
    low = text.lower()
    hits = [low.find(w) for w in words if low.find(w) >= 0]
    start = max(0, min(hits) - 80) if hits else 0
    piece = ("…" if start else "") + text[start:start + 240] + ("…" if start + 240 < len(text) else "")
    esc = e(piece)
    pat = "|".join(re.escape(e(w)) for w in sorted(set(words), key=len, reverse=True))
    return re.sub(f"({pat})", r"<mark>\1</mark>", esc, flags=re.I) if pat else esc


def search(snap: Snap, query: str):
    hits = rank(snap, query) if query.strip() else []
    words = query.lower().split()
    items = "".join(f'<li><a class="title" href="{page_url(c)}">{e(c["title"])}</a>'
                    f'<p class="sub">{e(snap.host_name(c.get("host", "")))} · {e(c.get("kind", ""))} · {chip(snap, c)}</p>'
                    f'<p>{snippet(c, words)}</p></li>' for c in hits)
    exact = any(c["title"].lower() == query.strip().lower() for c in snap.cards)
    create = "" if exact or not query.strip() else \
        f'<p>No page is called “{e(query.strip())}”. <a class="new" href="/special/new?title={q(query.strip())}">Create it</a>.</p>'
    main = ('<div class="titlebar"><h1>Search</h1></div>'
            f'<form class="bigsearch" action="/search" role="search"><input type="search" name="q" value="{e(query)}" '
            'aria-label="Search the atlas" placeholder="Search titles and text"><button class="btn primary">Search</button></form>'
            + (f'<p class="sub">{len(hits)} page{"s" if len(hits) != 1 else ""} match{"" if len(hits) != 1 else "es"}.</p>' if query.strip() else "")
            + create + (f'<ul class="results">{items}</ul>' if items else ""))
    return f"Search: {query}" if query else "Search", main, "", query


def suggest(snap: Snap, query: str) -> list[dict]:
    qn = query.strip().lower()
    if not qn:
        return []
    res = []
    for c in rank(snap, query)[:7]:
        extra = " · draft" if c["_folder"] == "inbox" else " · retired" if c["_folder"] == "retired" else ""
        res.append({"title": c["title"], "url": page_url(c), "sub": f"{snap.host_name(c.get('host', ''))} · {c.get('kind', '')}{extra}"})
    for k, name in snap.hosts.items():
        if qn in name.lower() or qn in k:
            res.append({"title": name, "url": f"/host/{q(k)}", "sub": "place"})
    for k in snap.kinds():
        if qn in k or qn in kind_label(k).lower():
            res.append({"title": kind_label(k), "url": f"/kind/{q(k)}", "sub": "kind"})
    for t, u, _ in SPECIAL:
        if qn in t.lower():
            res.append({"title": t, "url": u, "sub": "special page"})
    res = res[:9]
    res.append({"title": f"Search for “{query.strip()}”", "url": f"/search?q={q(query.strip())}", "sub": "every word, in every page"})
    return res


# ── main page, missing pages ─────────────────────────────────────────────────

def main_page(snap: Snap):
    att = A.attention(snap.active, snap.st)
    hosts = {c.get("host") for c in snap.active}
    look = "".join(f'<li>{link(c)}{chips(snap, c)}<span class="sub">{e(A.clip(why, 110))}</span></li>' for _, c, why in att[:8])
    evs, seen = [], set()
    for at, c, by, summary, key, older in events(snap, 60):
        if c["_slug"] in seen:
            continue
        seen.add(c["_slug"])
        evs.append(f'<li>{link(c)}<span class="sub when">{e(R.when(at))}</span><span class="sub">{e(summary or H.BY.get(by, by))}</span></li>')
        if len(evs) == 8:
            break
    blocks = []
    for h in [h for h in snap.hosts if h in hosts] + sorted(x for x in hosts if x not in snap.hosts):
        cs = sorted((c for c in snap.active if c.get("host") == h), key=lambda c: (c["_folder"] == "inbox", c["title"].lower()))
        more = f' · <a href="/host/{q(h)}">{len(cs) - 8} more</a>' if len(cs) > 8 else ""
        blocks.append(f'<section><h3><a href="/host/{q(h)}">{e(snap.host_name(h))}</a><span class="count">{len(cs)}</span></h3>'
                      f'<p>{" · ".join(link(c) for c in cs[:8])}{more}</p></section>')
    kinds_line = " · ".join(f'<a href="/kind/{q(k)}">{e(kind_label(k))}</a> <span class="sub">{sum(1 for c in snap.active if c.get("kind") == k)}</span>'
                            for k in snap.kinds())
    main = ('<div class="titlebar"><h1>Atlas</h1></div>'
            f'<p class="lead">What runs where, and why: {len(snap.active)} pages in {len(hosts)} places. '
            f'{len(att)} need a look; checks last ran {e(A.ago(A.last_checked(snap.st)))}.</p>' + notice(snap) +
            '<form class="bigsearch" action="/search" role="search"><input type="search" name="q" '
            'placeholder="Search every page" aria-label="Search every page"><input type="hidden" name="go" value="1">'
            '<button class="btn primary">Search</button></form>'
            '<div class="cols">'
            f'<section><h2>Needs a look</h2>{"<ul class=rows>" + look + "</ul>" if look else "<p class=empty>Nothing.</p>"}'
            f'<p><a href="/special/attention">All {len(att)}</a></p></section>'
            f'<section><h2>Recently changed</h2><ul class="rows">{"".join(evs)}</ul>'
            '<p><a href="/special/recent">All changes</a></p></section></div>'
            f'<h2>Places</h2><div class="places">{"".join(blocks)}</div>'
            f'<h2>Kinds</h2><p>{kinds_line}</p>')
    return "Atlas", main, "main", ""


def missing(snap: Snap, name: str):
    hits = rank(snap, name)[:8]
    main = (f'<div class="titlebar"><h1>{e(name)}</h1></div>'
            f'<p class="lead">There is no page called “{e(name)}” yet.</p>'
            f'<div class="buttons" style="margin-bottom:24px"><a class="btn primary" href="/special/new?title={q(name)}">Create it</a></div>'
            + (f"<h2>Pages that mention it</h2>{rows(snap, hits)}" if hits else ""))
    return name, main, "", ""


def not_found(snap: Snap, what="That page"):
    return "Not found", f'<div class="titlebar"><h1>Not found</h1></div><p class="lead">{e(what)} does not exist. ' \
                        '<a href="/">Go to the main page</a> or search above.</p>', "", ""
