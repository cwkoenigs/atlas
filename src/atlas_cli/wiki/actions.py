"""What the wiki's forms and buttons do. Each returns ("redirect", url, notice html) or ("page", view tuple).

Every write goes through core (A.save, A.promote, A.retire...), so the CLI and the wiki change cards the
same way and every change lands in the page's history.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re

from .. import core as A
from . import render as R
from . import views as V
from .render import e, page_url

LINE_FIELDS = ("title", "where", "what", "why", "source", "entry", "check")


def digest(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def ok(html: str) -> str:
    return f'<div class="notice" data-kind="ok"><p>{html}</p></div>'


def fail(html: str, extra: str = "") -> str:
    return f'<div class="notice" data-kind="fail"><p>{html}</p>{extra}</div>'


def one_line(v: str) -> str:
    return " ".join((v or "").split())


def _links(snap, text: str):
    """'Pi home server, old Mac' -> (ids, problem)."""
    ids, unknown = [], []
    text = (text or "").strip()
    names = [text] if text.lower() in snap.by_key else next(csv.reader([text], skipinitialspace=True))
    for name in [x.strip() for x in names if x.strip()]:
        c = snap.by_key.get(name.lower())
        (ids.append(c.get("id") or c["_slug"]) if c else unknown.append(name))
    return ids, (f"No page is called {', '.join(e(u) for u in unknown)}. Related pages must already exist." if unknown else "")


def _secret(values) -> str:
    for v in values:
        m = R.SECRET.search(v or "")
        if m:
            return ("That looks like a password, token or key (it starts "
                    f"<code>{e(m.group(0)[:8])}…</code>). Pages never hold secrets: name the account or where the "
                    "secret is kept instead.")
    return ""


def _posted(form) -> dict:
    v = {k: form.get(k, "") for k in ("title", "kind", "host", "where", "what", "why", "source", "entry", "check",
                                      "links", "confidence", "summary")}
    v["personal"] = "yes" if form.get("personal") == "yes" else ""
    v["body"] = form.get("body", "").replace("\r\n", "\n")
    return v


@A.transaction
def save_edit(snap, c, form):
    section = form.get("section")
    section = int(section) if section not in (None, "") and str(section).isdigit() else None
    current = A.read_text(c["_path"])
    base = form.get("base") or digest(c["_raw"])
    c = A.parse_text(current, c["_path"])
    problems = []
    if base != digest(current):
        problems.append("This page changed while you were editing it (the atlas command, an agent or another window "
                        "saved it). Your text is below; the newer version is in the history. Save again to keep yours.")
        base = digest(current)
    new = {k: v for k, v in c.items()}
    v = V.form_values(snap, c) if section is not None else _posted(form)
    v["body"] = form.get("body", "").replace("\r\n", "\n")
    v["summary"] = form.get("summary", "")
    if section is None:
        for k in LINE_FIELDS:
            new[k] = one_line(form.get(k, ""))
        new["kind"] = one_line(form.get("kind", "")) or c.get("kind", "")
        host = form.get("host", "")
        new["host"] = host if host in snap.hosts or host == c.get("host") else c.get("host", "")
        new["confidence"] = form.get("confidence") if form.get("confidence") in ("confirmed", "believed", "guess") else c.get("confidence", "")
        ids, prob = _links(snap, form.get("links", ""))
        if prob:
            problems.append(prob)
        new["links"] = ids
        if not new["title"]:
            problems.append("A page needs a title.")
        elif new["title"] != c["title"]:
            try:
                A.check_title(new["title"], c["_path"])
            except A.Conflict as ex:
                problems.append(e(ex))
            aliases = [a for a in (c.get("aliases") or []) if a.lower() != new["title"].lower()]
            new["aliases"] = aliases + [c["title"]]          # [[Old title]] keeps working, like a redirect
        new["_body"] = "\n" + v["body"].strip("\n") + "\n"
    else:
        parts = R.split_sections(c.get("_body", ""))
        if not 0 <= section < len(parts):
            problems.append("That section no longer exists; edit the whole page instead.")
            section = None
        else:
            new["_body"] = R.join_section(parts, section, v["body"])
    if section is None and (form.get("personal") == "yes") != c["_personal"]:
        try:
            A.move_destination(c, c["_folder"], form.get("personal") == "yes")
        except A.Conflict as ex:
            problems.append(e(ex))
    secret = _secret([new.get(k, "") for k in LINE_FIELDS] + [new.get("_body", "")])
    if secret:
        problems.append(secret)
    if form.get("do") == "preview" or problems:
        prev = V.preview_block(snap, new) if form.get("do") == "preview" and not secret else ""
        return "page", V.edit(snap, c, v, " ".join(problems), prev, section, base)
    summary = one_line(form.get("summary")) or ("edited a section" if section is not None else "edited")
    A.save(new, summary, by="wiki")
    if section is None and (form.get("personal") == "yes") != c["_personal"]:
        A.set_personal(A.parse(new["_path"]), form.get("personal") == "yes", by="wiki")
    A.rebuild()
    return "redirect", page_url(c), ok("Saved.")


def create_page(snap, form):
    v = _posted(form)
    title = one_line(v["title"])
    problems = []
    if not title:
        problems.append("A page needs a title.")
    elif A.slugify(title) in snap.by_slug or title.lower() in snap.by_key:
        other = snap.by_slug.get(A.slugify(title)) or snap.by_key.get(title.lower())
        problems.append(f'A page called <a href="{page_url(other)}">{e(other["title"])}</a> already exists.')
    ids, prob = _links(snap, v["links"])
    if prob:
        problems.append(prob)
    body = "\n" + v["body"].strip("\n") + "\n"
    fields = {k: one_line(v[k]) for k in ("where", "what", "why", "source", "entry", "check")}
    secret = _secret(list(fields.values()) + [title, body])
    if secret:
        problems.append(secret)
    host = v["host"] if v["host"] in snap.hosts else next(iter(snap.hosts))
    kind = one_line(v["kind"]) or "service"
    conf = v["confidence"] if v["confidence"] in ("confirmed", "believed", "guess") else "guess"
    if form.get("do") == "preview" or problems:
        prev = ""
        if form.get("do") == "preview" and not secret:
            fake = {**fields, "title": title or "Untitled", "kind": kind, "host": host, "confidence": conf, "links": ids,
                    "_body": body, "_slug": A.slugify(title) or "new", "_folder": "inbox", "_personal": bool(v["personal"]),
                    "_path": A.ROOT / "inbox" / "new.md"}
            prev = V.preview_block(snap, fake)
        return "page", V.new_page(snap, v, " ".join(problems), prev)
    c = A.new_card(title, kind, host, personal=bool(v["personal"]), confidence=conf, body=body, by="wiki",
                   summary=one_line(v["summary"]) or "created in the wiki", links=ids, **fields)
    A.rebuild()
    return "redirect", page_url(c), ok("Created. It is a draft until you promote it.")


def _checks(cards):
    """Run checks; a result macOS blocked (privacy settings) is not a real failure, so keep the old one."""
    blocked = []
    def accept(c, result):
        if not result["ok"] and "Operation not permitted" in result["out"]:
            blocked.append(c)
            return False
        return True
    st = A.run_checks(cards, accept_result=accept)
    return st, blocked


def do_action(snap, c, form):
    action = form.get("action", "")
    url = page_url(c)
    if action == "check":
        if not c.get("check"):
            return "redirect", url, fail("This page has no check yet. Edit it to add one.")
        st, blocked = _checks([c])
        A.rebuild()
        if blocked:
            return "redirect", url, fail("macOS did not let the wiki read what the check needs. In a terminal, "
                                         f"<code>atlas check {e(c['_slug'])}</code> runs it with your permissions.")
        res = st.get(c["id"], {})
        if res.get("ok"):
            return "redirect", url, ok("Check passed: this page is still true.")
        return "redirect", url, fail(f"Check failed: <code>{e(res.get('out') or 'no output')}</code>")
    if action == "confirm":
        A.confirm(c, by="wiki")
        A.rebuild()
        return "redirect", url, ok(f"Confirmed: still true on {A.TODAY.isoformat()}.")
    if action in ("promote", "promote-force"):
        dest, problem = A.promote(c, force=action == "promote-force", by="wiki")
        A.rebuild()
        if problem:
            anyway = (f'<form method="post" action="{url}/do">{V.token_input()}'
                      '<button class="btn" name="action" value="promote-force">Promote anyway</button></form>')
            return "redirect", url, fail(f"Not promoted: {e(problem)}. Fix the page, or promote it anyway if it is "
                                         "known to be down right now.", anyway)
        return "redirect", url, ok("Promoted: it is on the map now.")
    if action in ("personal", "share"):
        A.set_personal(c, action == "personal", by="wiki")
        return "redirect", url, ok("Personal now: it stays on this Mac, out of git." if action == "personal"
                                   else "Shared now: it goes to git with the other pages on the next commit.")
    if action == "retire":
        reason = one_line(form.get("reason", ""))
        A.retire(c, reason, by="wiki")
        A.rebuild()
        return "redirect", url, ok("Retired. The page stays, under Retired pages, with its history.")
    if action == "unretire":
        A.unretire(c, by="wiki")
        A.rebuild()
        return "redirect", url, ok("Back, as a draft: check it, then promote it.")
    return "redirect", url, fail("The wiki does not know that action.")


def restore(snap, c, form):
    r = V.find_rev(c, form.get("key", ""))
    if not r:
        return "redirect", page_url(c) + "/history", fail("That version is not in the history any more.")
    text = R.revision_text(r)
    try:
        A.parse_text(text, c["_path"])
    except ValueError:
        return "redirect", page_url(c) + "/history", fail("That version could not be read.")
    A.save(c, f"restored the version from {R.when(r['at'])}", by="wiki", text=text)
    A.rebuild()
    return "redirect", page_url(c), ok(f"Restored the version from {e(R.when(r['at']))}. The one it replaced is in the history.")


def check_all(snap):
    cards = snap.active
    st, blocked = _checks(cards)
    A.rebuild()
    fails = sum(1 for c in cards if c.get("check") and not st.get(c["id"], {}).get("ok", True))
    note = f" macOS blocked {len(blocked)}; run <code>atlas check</code> in a terminal for those." if blocked else ""
    return "redirect", "/special/attention", (fail if fails else ok)(
        f"Checked {sum(1 for c in cards if c.get('check'))} pages: " + (f"{fails} failing." if fails else "all passing.") + note)
