"""atlas: what runs where, and why. The terminal interface, in the ds-next terminal design system.

Every line is built with ui_style (roles, glyphs, the 80-column grid); widgets are framed because a
frame means "needs you". Cards are addressed by their number on the map or a word from their name.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import textwrap
import time

from rich.text import Text

from . import core as A
from . import ui_style as S
from . import widgets as W
from .picker import browse
from .ui_style import G, LABEL_W

VERSION = "0.2"
TTY = sys.stdout.isatty() and sys.stdin.isatty()
out = S.console(color=sys.stdout.isatty())
VALUE_COL = 2 + LABEL_W + 1          # where labelled values start (col 16)


# ── small builders ───────────────────────────────────────────────────────────

def mark(state: str) -> Text:
    """The outcome glyph for a card's state: ✓ ok · ✗ failing · ⚠ new or unchecked."""
    kind = {"ok": "ok", "fail": "err"}.get(state, "warn")
    return Text(getattr(G, kind), style=kind)


def labelled_wrap(label: str, value: str, style: str = "") -> None:
    """A labelled row whose value wraps under the value column, never under the label."""
    width = S.width(out) - VALUE_COL
    lines = textwrap.wrap(value, width, break_on_hyphens=False, break_long_words=False) or [""]
    out.print(S.labelled(label, Text(lines[0], style=style)))
    for more in lines[1:]:
        out.print(Text(" " * VALUE_COL + more, style=style))


def say_error(what: str, fix: str = "") -> None:
    for line in S.error(what, fix):
        out.print(line)


def num_of(cards) -> dict:
    return A.numbers(cards)


# ── the map ──────────────────────────────────────────────────────────────────

def reason(why: str) -> str:
    return A.clip(why.split(";")[0], 44)


def print_map(cards, st) -> None:
    lst = A.ordered(cards)
    num = num_of(cards)
    tw = min(max(len(c["title"]) for c in lst), 28) + 2
    row_w = S.width(out)

    def row(c, note: str, note_style: str = "muted") -> Text:
        _, s = A.status(c, st)
        t = Text.assemble(mark(s), " ", (f"{num[c['_slug']]:>2}", "dim"), "  ",
                          (A.clip(c["title"], tw - 2).ljust(tw), "bold" if s == "fail" else ""))
        t.append(A.clip(note, row_w - t.cell_len), note_style)
        return t

    att = A.attention(lst, st)
    if att:
        out.print(Text("needs a look", style="dim"))
        for _, c, why in att:
            out.print(row(c, reason(why), "err" if why.startswith("not ok") else "warn"))
        out.print()
    host = None
    for c in lst:
        if c.get("host") != host:
            if host is not None:
                out.print()
            host = c.get("host")
            out.print(Text(A.host_name(host).lower(), style="dim"))
        out.print(row(c, c.get("what", "")))
    counts = {k: sum(1 for c in lst if A.status(c, st)[1] == k) for k in ("ok", "fail", "draft")}
    facts = [f"{len(lst)} things", f"{counts['fail']} failing" if counts["fail"] else "nothing failing"]
    if counts["draft"]:
        facts.append(f"{counts['draft']} new")
    facts.append(f"checked {A.ago(A.last_checked(st))}")
    out.print()
    out.print(S.footer(*facts))


# ── one card ─────────────────────────────────────────────────────────────────

def print_card(c, cards, st) -> None:
    word, s = A.status(c, st)
    num = num_of(cards).get(c["_slug"], "?")
    head = Text.assemble(mark(s), " ", (c["title"], "bold"), "  ",
                         (G.sep.join(x for x in (c.get("kind", ""), A.host_name(c.get("host", "")).lower(),
                                                 "this mac only" if c["_personal"] else "") if x), "muted"))
    out.print(head)
    sv = A.short_version(c)
    if sv:
        for line in textwrap.wrap(sv, S.width(out) - S.INDENT, break_on_hyphens=False):
            out.print(Text(" " * S.INDENT + line))
    out.print()
    for label, k in (("where", "where"), ("what", "what"), ("why", "why"), ("edit it at", "source"), ("get to it", "entry")):
        if c.get(k):
            labelled_wrap(label, c[k])
    res = st.get(c.get("id"))
    if res:
        if res["ok"]:
            labelled_wrap("last check", f"passed{G.sep}{A.ago(res['at'])}", "ok")
        else:
            labelled_wrap("last check", f"failed{G.sep}{A.ago(res['at'])}" + (f"{G.sep}{res['out']}" if res["out"] else ""), "err")
    idx = {x.get("id"): x for x in cards} | {x["_slug"]: x for x in cards}
    nums = num_of(cards)
    rel = [f"{nums.get(idx[l]['_slug'], '?')} {idx[l]['title']}" for l in c.get("links", []) if l in idx]
    if rel:
        labelled_wrap("related", G.sep.join(rel), "muted")
    out.print()
    out.print(S.hint(f"atlas open {num} shows the whole card, with how it was untangled"))


# ── resolving a card from what was typed ────────────────────────────────────

def resolve(query: str, cards=None):
    """One card from a number or words; a picker when several match (on a terminal)."""
    cards = cards if cards is not None else A.load()
    try:
        return A.find(query, cards)
    except A.NoMatch:
        say_error(f"nothing matches {query!r}", "atlas shows everything · atlas <number> reads one")
        sys.exit(1)
    except A.Ambiguous as e:
        num = num_of(cards)
        if TTY:
            st = A.state()
            slug = asyncio.run(browse(f"{len(e.hits)} match {query!r}", e.hits, st, num))
            if slug is None:
                sys.exit(0)
            return next(c for c in e.hits if c["_slug"] == slug)
        say_error(f"{len(e.hits)} cards match {query!r}", "pick one by number:")
        for c in e.hits:
            out.print(Text(f"  {num.get(c['_slug'], '?'):>3}  {c['title']}", style="dim"))
        sys.exit(1)


# ── commands ─────────────────────────────────────────────────────────────────

def checks(cards, quiet: bool = False):
    """Run checks with the one live line; print an outcome per card unless quiet."""
    todo = [c for c in cards if c.get("check")]
    started = time.monotonic()
    results = []
    with out.status(S.status_label("checking", 0), spinner=S.SPINNER, spinner_style="accent") as live:
        def each(c, ok, detail):
            results.append((c, ok, detail))
            live.update(S.status_label(f"checked {len(results)} of {len(todo)}", int(time.monotonic() - started)))
        st = A.run_checks(todo, on_each=each)
    if not quiet:
        for c, ok, detail in results:
            out.print(S.outcome("ok" if ok else "err", c["title"], "" if ok else detail))
    return st


def cmd_map(args) -> None:
    cards = A.load()
    st = A.state()
    if args.check or not A.fresh(st):
        st = checks([c for c in cards if c["_folder"] != "retired"], quiet=True)
        A.rebuild(cards, st)
    if TTY:
        lst = A.ordered(cards)
        att = A.attention(lst, st)
        fails = sum(1 for c in lst if A.status(c, st)[1] == "fail")
        facts = [("things", str(len(lst))), ("needs a look", str(len(att))), ("failing", str(fails)),
                 ("checked", A.ago(A.last_checked(st))), ("places", str(len({c.get('host') for c in lst})))]
        hints = ["type to filter · enter opens", "atlas new adds a card", "atlas help lists the rest"]
        for line in S.banner(VERSION, facts, hints, str(A.ROOT).replace(os.path.expanduser("~"), "~"),
                             "what runs where", w=S.width(out), name="atlas"):
            out.print(line)
        out.print()
    print_map(cards, st)
    if TTY:
        browse_loop(cards, st)
    else:
        out.print(S.hint("atlas <number> or atlas <word> reads one · atlas help lists the rest"))


def browse_loop(cards, st) -> None:
    lst = A.ordered(cards)
    num = num_of(cards)
    while True:
        out.print()
        slug = asyncio.run(browse("open a card", lst, st, num))
        if slug is None:
            return
        c = next(x for x in lst if x["_slug"] == slug)
        out.print()
        print_card(c, cards, st)


def cmd_show(args) -> None:
    cards = A.load()
    print_card(resolve(" ".join(args.query), cards), cards, A.state())


def cmd_check(args) -> None:
    cards = [c for c in A.load() if c["_folder"] != "retired"]
    if args.query:
        cards = [resolve(" ".join(args.query), cards)]
    st = checks(cards)
    A.rebuild(A.load(), st)
    lst = A.ordered(A.load())
    fails = sum(1 for c in cards if not st.get(c["id"], {}).get("ok", True))
    out.print(S.footer(f"{len(cards)} checked", f"{fails} failing" if fails else "all ok", "pages rebuilt"))


def cmd_new(args) -> None:
    hosts = list(A.CFG["hosts"].items())
    kinds = ["site", "app", "service", "job", "repo", "folder", "domain", "device"]
    if args.title and not TTY:
        values = {"title": args.title, "kind": args.kind or "service", "host": args.host or hosts[0][0],
                  "personal": "yes" if args.personal else "no"}
    else:
        if not TTY:
            say_error("atlas new needs a terminal, or a title and flags", "atlas new \"Title\" --kind site --host vercel")
            sys.exit(1)
        fields = [
            W.Field("title", "title", args.title or "", required=True, example="Ringneck billing site"),
            W.Field("kind", "kind", args.kind or "service", choices=[(k, k) for k in kinds]),
            W.Field("host", "place", args.host or hosts[0][0], choices=[(k, v.lower()) for k, v in hosts]),
            W.Field("where", "where", hint="the exact place: path, project, URL"),
            W.Field("what", "what", hint="one line: what it does"),
            W.Field("why", "why", hint="one line: why it exists; leave empty if unknown"),
            W.Field("source", "edit it at", hint="the source of truth: repo and path"),
            W.Field("entry", "get to it", hint="a URL or a command"),
            W.Field("check", "check", hint="a command that succeeds only while this card is true",
                    example="curl -fsS -o /dev/null -m 10 https://…"),
            W.Field("personal", "personal", "yes" if args.personal else "no",
                    choices=[("no", "no, share it in git"), ("yes", "yes, this mac only")]),
        ]
        values = asyncio.run(W.form("new card", fields,
                                    footer=lambda v: f"a draft in the inbox{G.sep}promote it once it is confirmed",
                                    validate=lambda v: None, width=S.width(out)))
        if values is None:
            out.print(S.hint("cancelled · nothing written"))
            return
    personal = values.pop("personal") == "yes"
    try:
        c = A.new_card(values.pop("title"), values.pop("kind"), values.pop("host"), personal=personal,
                       confidence="believed" if values.get("why") else "guess", **values)
    except ValueError as e:
        say_error(str(e), "atlas <word> finds the existing card")
        sys.exit(1)
    n = num_of(A.load()).get(c["_slug"], "?")
    out.print(S.outcome("ok", f"drafted {c['title']}", f"number {n}{G.sep}in the inbox" + (f"{G.sep}this mac only" if personal else "")))
    out.print(S.hint(f"atlas open {n} adds the story · atlas promote {n} once it is confirmed"))


def cmd_promote(args) -> None:
    c = resolve(" ".join(args.query))
    dest, problem = A.promote(c, force=args.force)
    if problem:
        say_error(f"{c['title']} not promoted: {problem}", "fix the card (atlas open) or use --force for something known to be down")
        sys.exit(1)
    out.print(S.outcome("ok", f"promoted {c['title']}", "confirmed today"))


def cmd_confirm(args) -> None:
    c = resolve(" ".join(args.query))
    A.confirm(c)
    out.print(S.outcome("ok", f"confirmed {c['title']}", A.TODAY.isoformat()))


def cmd_retire(args) -> None:
    c = resolve(" ".join(args.query))
    A.retire(c, args.reason or "")
    out.print(S.outcome("ok", f"retired {c['title']}", args.reason or "kept in retired/"))


def cmd_personal(args) -> None:
    c = resolve(" ".join(args.query))
    dest = A.set_personal(c, not args.undo)
    if dest is None:
        out.print(S.outcome("warn", c["title"], "already " + ("this mac only" if not args.undo else "shared")))
    else:
        out.print(S.outcome("ok", c["title"], "this mac only, not in git" if not args.undo else "shared, in git"))


def cmd_open(args) -> None:
    c = resolve(" ".join(args.query))
    if args.edit and os.environ.get("EDITOR"):
        os.execvp(os.environ["EDITOR"], [os.environ["EDITOR"], str(c["_path"])])
    subprocess.run(["open", str(c["_path"])])
    out.print(S.outcome("ok", f"opened {c['title']}", str(c["_path"].relative_to(A.ROOT))))


def cmd_page(args) -> None:
    page = A.expand(A.CFG.get("html_out", ""))
    target = page if page.is_file() else A.ROOT / "ATLAS.md"
    subprocess.run(["open", str(target)])
    out.print(S.outcome("ok", "opened the card page", str(target).replace(os.path.expanduser("~"), "~")))


def cmd_lint(args) -> None:
    cards, problems = A.lint()
    if not problems:
        out.print(S.outcome("ok", "lint", f"{len(cards)} cards"))
        return
    for p in problems:
        out.print(S.outcome("warn", p))
    sys.exit(1)


HELP = [
    ("atlas", "the map; on a terminal, a picker to open cards"),
    ("atlas 5", "read card 5 · atlas pi reads the card named pi"),
    ("atlas open 5", "the whole card, with how it was untangled"),
    ("atlas new", "draft a card (a form on a terminal)"),
    ("atlas check", "re-run every check now · atlas check 5 for one"),
    ("atlas promote 5", "inbox to cards, once it is confirmed"),
    ("atlas confirm 5", "you re-read it and it is still true"),
    ("atlas retire 5", "the thing is gone · --reason \"…\""),
    ("atlas personal 5", "keep it on this mac only · --undo shares it"),
    ("atlas page", "open the card page in the browser"),
    ("atlas lint", "missing fields, unknown places, broken links"),
]


def cmd_help(args=None) -> None:
    out.print(Text.assemble(("atlas", "brand bold"), (f" {VERSION}", "dim"), ("  what runs where, and why", "muted")))
    out.print()
    cw = max(len(cmd) for cmd, _ in HELP) + 2
    for cmd, what in HELP:
        out.print(Text.assemble("  ", (cmd.ljust(cw), "bold"), (what, "muted")))
    out.print()
    out.print(S.hint("a card is its number on the map or a word from its name"))
    out.print(S.hint("--plain prints without colour or widgets"))


COMMANDS = {"new": cmd_new, "check": cmd_check, "promote": cmd_promote, "confirm": cmd_confirm,
            "retire": cmd_retire, "personal": cmd_personal, "open": cmd_open, "page": cmd_page,
            "lint": cmd_lint, "help": cmd_help, "show": cmd_show, "today": cmd_map, "map": cmd_map}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="atlas", add_help=False)
    sub = p.add_subparsers(dest="cmd")
    for name in ("map", "today"):
        s = sub.add_parser(name, add_help=False)
        s.add_argument("--check", action="store_true"); s.add_argument("--plain", action="store_true")
        s.add_argument("--no-check", action="store_true")
    s = sub.add_parser("new", add_help=False)
    s.add_argument("title", nargs="?"); s.add_argument("--kind"); s.add_argument("--host")
    s.add_argument("--personal", action="store_true")
    for name in ("show", "promote", "confirm", "retire", "personal", "open"):
        s = sub.add_parser(name, add_help=False); s.add_argument("query", nargs="+")
        if name == "promote": s.add_argument("--force", action="store_true")
        if name == "retire": s.add_argument("--reason")
        if name == "personal": s.add_argument("--undo", action="store_true")
        if name == "open": s.add_argument("--edit", action="store_true")
    s = sub.add_parser("check", add_help=False); s.add_argument("query", nargs="*")
    for name in ("page", "lint", "help"):
        sub.add_parser(name, add_help=False)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    global TTY
    if "--plain" in argv:
        TTY = False
        argv = [a for a in argv if a != "--plain"]
    if argv and argv[0] in ("-h", "--help"):
        argv = ["help"]
    if not argv:
        argv = ["map"]
    elif argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv = ["show"] + argv                       # `atlas 5`, `atlas pi`, `atlas billing site`
    try:
        args = parser().parse_args(argv)
    except SystemExit:
        say_error("that is not an atlas command", "atlas help lists them")
        sys.exit(2)
    try:
        COMMANDS[args.cmd](args)
    except KeyboardInterrupt:
        out.print(S.hint("interrupted"))
        sys.exit(130)


if __name__ == "__main__":
    main()
