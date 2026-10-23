"""ds-next terminal style: colour roles, glyphs, grid, line builders, frames.

Copied from the ds-next terminal design system v1 (2026-10-23, ~/Downloads/CLI design system development prod.zip,
final/code/ui_style.py). Only change: banner() takes the product name. Do not add colours or glyphs here.

Everything the terminal prints goes through this module so the roles and columns stay
consistent. Design reference: "ds-next Screens" (rail + Cortex chrome).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from rich.console import Console, RenderableType
from rich.spinner import SPINNERS
from rich.text import Text
from rich.theme import Theme

# ── colour roles: (dark truecolor, light truecolor, ansi-16 fallback) ────────
PALETTE = {
    "text":    ("#e7e7ea", "#1d1f20", "default"),
    "muted":   ("#98989b", "#5d5d60", "bright_black"),
    "dim":     ("#7a7a7d", "#7a7a7d", "bright_black"),
    "rule":    ("#424244", "#d4d4d7", "bright_black"),
    "accent":  ("#94bce3", "#416180", "cyan"),
    "strong":  ("bold #b5d9fd", "bold #2c455d", "bold cyan"),
    "brand":   ("#749dc4", "#5980a6", "blue"),
    "ok":      ("#7fd4a0", "#2f7d4f", "green"),
    "warn":    ("#e3c56b", "#8a6a12", "yellow"),
    "err":     ("#ef8a7a", "#b3402e", "red"),
    "band":    ("bold #1d1f20 on #749dc4", "bold #f2f2f3 on #5980a6", "bold black on blue"),
    "key":     ("bold #1d1f20 on #94bce3", "bold #f2f2f3 on #416180", "bold black on cyan"),
    "surface": ("on #2b2b2d", "on #e9e9ea", "on bright_black"),
    "hl":      ("on #2c455d", "on #c9dcee", "reverse"),
    "eye":     ("#1d1f20", "#f2f2f3", "black"),          # mascot eyes: the terminal ground
    "on_brand": ("on #749dc4", "on #5980a6", "on blue"),
    "on_strong": ("on #b5d9fd", "on #2c455d", "on cyan"),
    "on_eye":  ("on #1d1f20", "on #f2f2f3", "on black"),
}


def is_dark() -> bool:
    return os.environ.get("DS_THEME", "dark") != "light"


def truecolor() -> bool:
    return os.environ.get("COLORTERM", "") in ("truecolor", "24bit")


def theme(*, color: bool = True) -> Theme:
    """Rich Theme for this terminal. DS_THEME=light|dark picks the ramp."""
    dark, tc = is_dark(), truecolor()
    styles = {}
    for role, (d, l, ansi) in PALETTE.items():
        if not color:
            styles[role] = "bold" if role in ("strong", "band", "key") else ""
        else:
            styles[role] = (d if dark else l) if tc else ansi
    return Theme(styles)


def console(*, color: bool = True, **kw) -> Console:
    return Console(theme=theme(color=color), highlight=False, **kw)


_ANSI = {"default": "", "black": "ansiblack", "red": "ansired", "green": "ansigreen", "yellow": "ansiyellow",
         "blue": "ansiblue", "magenta": "ansimagenta", "cyan": "ansicyan", "white": "ansiwhite",
         "bright_black": "ansibrightblack", "dim": ""}


def _pt(style: str) -> str:
    """Rich style syntax → prompt_toolkit: `bold #1d1f20 on #749dc4` → `bold #1d1f20 bg:#749dc4`,
    `on blue` → `bg:ansiblue`, `reverse` kept."""
    out, toks = [], style.split()
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "on" and i + 1 < len(toks):
            c = toks[i + 1]
            out.append("bg:" + (c if c.startswith("#") else _ANSI.get(c, c)))
            i += 2
            continue
        out.append(t if t.startswith("#") or t in ("bold", "italic", "underline", "reverse") else _ANSI.get(t, t))
        i += 1
    return " ".join(x for x in out if x)


def pt_style() -> dict[str, str]:
    """The same roles for prompt_toolkit (prompt, completion menu, widgets), translated."""
    dark, tc = is_dark(), truecolor()
    col = {r: _pt((v[0] if dark else v[1]) if tc else v[2]) for r, v in PALETTE.items()}
    bg, fg, sf = ("#1d1f20", "#e7e7ea", "#2b2b2d") if dark else ("#f2f2f3", "#1d1f20", "#e9e9ea")
    return {
        "prompt": col["strong"], "rule": col["rule"], "band": col["band"], "key": col["key"],
        "dim": col["dim"], "muted": col["muted"], "accent": col["accent"], "strong": col["strong"],
        "err": col["err"], "ok": col["ok"], "warn": col["warn"], "label": col["dim"],
        "focus": col["strong"], "title": "bold", "field": "", "error": col["err"],
        "frame.border": col["dim"], "frame.label": "bold",
        "bottom-toolbar": f"bg:{sf} {col['dim']}", "bottom-toolbar.text": f"bg:{sf} {col['dim']}",
        "completion-menu": f"bg:{bg} {col['muted']}",
        "completion-menu.completion": f"bg:{bg} {fg}",
        "completion-menu.completion.current": f"{col['hl']} {fg} bold",
        "completion-menu.meta.completion": f"bg:{bg} {col['muted']}",
        "completion-menu.meta.completion.current": f"{col['hl']} {fg}",
        "scrollbar.background": f"bg:{bg}", "scrollbar.button": f"bg:{sf}",
    }


# ── glyphs ───────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _Glyphs:
    prompt: str = "›"    # you              strong  col 1
    agent: str = "●"     # agent text       accent  col 1
    run: str = "→"       # tool call        muted   col 3
    result: str = "⎿"    # first result     dim     col 5
    rail: str = "│"      # continuation     rule    col 1
    close: str = "╰"     # turn footer      rule    col 1
    ok: str = "✓"
    warn: str = "⚠"
    err: str = "✗"
    select: str = "❯"    # focused row      strong  col 2
    sep: str = " · "
    fold: str = "┄"


G = _Glyphs()
SPINNERS["ds"] = {"interval": 125, "frames": list("◐◓◑◒")}
SPINNER = "ds"

# ── grid ─────────────────────────────────────────────────────────────────────
INDENT = 2           # agent text, tool calls      → col 3
RESULT_INDENT = 4    # tool results                → col 5
LABEL_W = 12         # forms, /status, reconcile   → values at col 16
DESIGN_WIDTH = 80


def width(c: Console) -> int:
    return max(60, min(c.width, DESIGN_WIDTH))


# ── line builders ────────────────────────────────────────────────────────────
def you(line: str) -> Text:
    return Text.assemble((G.prompt, "strong"), " ", line)


def agent_lines(c: Console, body: RenderableType) -> None:
    """● on the first line, │ on the rest; body may be Markdown. Wraps under col 3."""
    lines = c.render_lines(body, c.options.update_width(width(c) - INDENT), pad=False)
    for i, segs in enumerate(lines):
        head = Text(G.agent + " ", style="accent") if i == 0 else Text(G.rail + " ", style="rule")
        c.print(head, Text.assemble(*((s.text, s.style or "") for s in segs)).rstrip(), sep="")


def run(tool: str, arg: str = "") -> Text:
    t = Text.assemble((G.rail, "rule"), " ", (G.run, "muted"), " ", (tool, "bold"))
    if arg:
        t.append(" ").append(arg, "muted")
    return t


def result(first: str, more: int = 0, *, error: bool = False, key: str = "ctrl-o") -> Text:
    style = "err" if error else "dim"
    t = Text.assemble((G.rail, "rule"), " " * (RESULT_INDENT - 1), (f"{G.result} {first}", style))
    if more:
        t.append(f"  {G.fold} {more} more lines{G.sep}{key}", "dim")
    return t


def outcome(kind: str, subject: str, detail: str = "") -> Text:
    """kind in ok|warn|err — closes a block, never opens one. No rail: local commands are flat."""
    t = Text.assemble((getattr(G, kind), kind), " ", (subject, "bold"))
    if detail:
        t.append("  ").append(detail, "muted")
    return t


def footer(*facts: str) -> Text:
    return Text.assemble((G.close, "rule"), " ", (G.sep.join(facts), "dim"))


def status_label(step: str, secs: int) -> str:
    """Markup for console.status: the one live line, redrawn in place."""
    return f"[muted]{step}[/][dim]{G.sep}{secs}s{G.sep}ctrl-c interrupts[/]"


def labelled(label: str, value: Text | str, *, indent: int = 2, style: str = "dim") -> Text:
    t = Text(" " * indent).append(f"{label:<{LABEL_W}} ", style=style)
    return t.append_text(value if isinstance(value, Text) else Text(value))


def hint(text: str) -> Text:
    return Text(" " * INDENT + text, style="dim")


def fold(text: str) -> Text:
    return Text(" " * INDENT + f"{G.fold} {text}", style="dim")


def error(what: str, fix: str = "") -> list[Text]:
    """Red only on the line that failed; the fix follows in dim."""
    out = [Text.assemble((G.err, "err"), " ", what)]
    if fix:
        out.append(hint(fix))
    return out


# ── the mascot: dog (steel) and cat (light accent), arms around each other ─────
# 28×20 pixels, drawn with half-blocks so each text row carries two pixel rows.
# D dog · C cat · k eye/nose (terminal background) · . empty
MASCOT = """\
............................
................C......C....
....DDDDDD......CC....CC....
..DDDDDDDDDD....CCCCCCCCC...
.DDDDDDDDDDDD..CCCCCCCCCCC..
.DDDDDDDDDDDD..CCCCCCCCCCC..
.DDDkkDDDkkDD..CCkkCCCCkkC..
.DDDkkDDDkkDD..CCkkCCCCkkC..
.DDDDDDDDDDDD..CCCCCCCCCCC..
.DDDDDkkDDDDD..CCCCCkkCCCC..
.DD.DDDDDD.DD...CCCCCCCCC...
....DDDDDD........CCCCC.....
..CCCDDDDDDDDDCCCCCCCCCDDD..
..CDDDDDDDDDDDCCCCCCCCCCCD..
..DDDDDDDDDDD..CCCCCCCCCC...
..DDDDDDDDDDD..CCCCCCCCCC.C.
..DDDDDDDDDDD..CCCCCCCCCCCC.
..DDDDDDDDDDD..CCCCCCCCCC...
..DDD..DDD.....CCC..CCC.....
..DDD..DDD.....CCC..CCC.....
""".splitlines()
_INK = {"D": "brand", "C": "strong", "k": "eye"}


def mascot_lines() -> list[Text]:
    """MASCOT as 10 Rich lines of ▀▄█: top pixel = foreground, bottom pixel = background."""
    out = []
    for top, bot in zip(MASCOT[0::2], MASCOT[1::2]):
        t = Text()
        for a, b in zip(top, bot):
            ia, ib = _INK.get(a), _INK.get(b)
            if not ia and not ib:
                t.append(" ")
            elif ia == ib:
                t.append("█", style=ia)
            elif ia and ib:
                t.append("▀", style=f"{ia} on_{ib}")
            elif ia:
                t.append("▀", style=ia)
            else:
                t.append("▄", style=ib)
        out.append(t)
    return out


# ── frames: a frame means "needs you" ────────────────────────────────────────
def frame(title: Text | str, rows: list[Text | None], *, kind: str = "input", keys: Text | None = None,
          w: int = DESIGN_WIDTH, prefix: Text | None = None) -> list[Text]:
    """Square frame, exact width. kind = input (dim edge) | approval (warn edge).
    `prefix` is printed before every line (the rail, inside a turn)."""
    edge = "warn" if kind == "approval" else "dim"
    pre = prefix or Text()
    iw = w - pre.cell_len
    title = Text(title) if isinstance(title, str) else title
    out = [Text.assemble(pre, ("┌─ ", edge), title, (" " + "─" * (iw - 5 - title.cell_len) + "┐", edge))]
    for r in rows:
        r = Text() if r is None else r.copy()
        r.truncate(iw - 4)
        r.pad_right(iw - 4 - r.cell_len)
        out.append(Text.assemble(pre, ("│ ", edge), r, (" │", edge)))
    if keys is not None:
        out.append(Text.assemble(pre, ("└─ ", edge), keys, (" " + "─" * (iw - 5 - keys.cell_len) + "┘", edge)))
    else:
        out.append(Text.assemble(pre, ("└" + "─" * (iw - 2) + "┘", edge)))
    return out


def banner(version: str, facts: list[tuple[str, str]], hints: list[str], path: str, tagline: str,
           w: int = DESIGN_WIDTH, name: str = "ds-next") -> list[Text]:
    """Two-pane frame shown once: word-mark left, facts right, path on a footer row."""
    li = 30
    ri = w - 3 - li
    title = Text.assemble((name, "brand bold"), (f" {version}", "dim"))
    e = "dim"
    out = [Text.assemble(("┌─ ", e), title, (" " + "─" * (li - 3 - title.cell_len) + "┬" + "─" * ri + "┐", e))]
    left: list[Text] = mascot_lines() + [
        Text(), Text.assemble("  ", (name, "bold"), (" · " + tagline, "muted"))]
    right: list[Text] = [Text()] + [Text.assemble(("  " + f"{k:<{LABEL_W}} ", "dim"), v) for k, v in facts] + [Text()]
    right += [Text("  " + h, style="dim") for h in hints]
    for i in range(max(len(left), len(right))):
        l_ = (left[i] if i < len(left) else Text()).copy()
        r_ = (right[i] if i < len(right) else Text()).copy()
        l_.truncate(li); l_.pad_right(li - l_.cell_len)
        r_.truncate(ri); r_.pad_right(ri - r_.cell_len)
        out.append(Text.assemble(("│", e), l_, ("│", e), r_, ("│", e)))
    out.append(Text("├" + "─" * li + "┴" + "─" * ri + "┤", style=e))
    lp = (w - 2 - len(path)) // 2
    out.append(Text.assemble(("│", e), " " * lp, (path, "muted"), " " * (w - 2 - lp - len(path)), ("│", e)))
    out.append(Text("└" + "─" * (w - 2) + "┘", style=e))
    return out


def toolbar(left: str, right: str, w: int) -> list[tuple[str, str]]:
    """prompt_toolkit bottom_toolbar fragments: one quiet band, facts left, context right."""
    gap = max(1, w - len(left) - len(right) - 4)
    return [("class:bottom-toolbar", f"  {left}{' ' * gap}{right}  ")]
