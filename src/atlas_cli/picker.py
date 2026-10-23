"""A filterable card picker, drawn like the design system's widgets.pick: inline, square frame
(a frame means "needs you"), focus is ❯ in strong, the submit key is the one filled band, and it
erases itself when done. Type to filter, ↑/↓ to move, Enter opens, Esc quits.
"""
from __future__ import annotations

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from . import core as A
from . import ui_style as S
from .ui_style import G

STYLE = Style.from_dict(S.pt_style())
VISIBLE = 10


def _matches(cards, query: str, num):
    words = query.lower().split()
    if not words:
        return list(cards)
    if len(words) == 1 and words[0].isdigit():
        return [c for c in cards if str(num.get(c["_slug"])).startswith(words[0])]
    hay = lambda c: f"{c['title']} {c.get('what', '')} {A.host_name(c.get('host', ''))} {c.get('kind', '')}".lower()
    return [c for c in cards if all(w in hay(c) for w in words)]


async def browse(title: str, cards, st, num) -> str | None:
    """Returns the chosen card's slug, or None on Esc / Ctrl-C."""
    state = {"i": 0, "top": 0}
    query = TextArea(multiline=False, wrap_lines=False, prompt=[("class:strong", f"{G.prompt} ")],
                     style="class:field")

    def shown():
        return _matches(cards, query.text, num)

    def on_change(_):
        state["i"], state["top"] = 0, 0
    query.buffer.on_text_changed += on_change

    kb = KeyBindings()

    def move(step: int):
        n = len(shown())
        if not n:
            return
        state["i"] = (state["i"] + step) % n
        if state["i"] < state["top"]:
            state["top"] = state["i"]
        elif state["i"] >= state["top"] + VISIBLE:
            state["top"] = state["i"] - VISIBLE + 1

    @kb.add("up", eager=True)
    @kb.add("c-p", eager=True)
    def _up(e):
        move(-1)

    @kb.add("down", eager=True)
    @kb.add("c-n", eager=True)
    @kb.add("tab", eager=True)
    def _down(e):
        move(1)

    @kb.add("enter", eager=True)
    def _enter(e):
        rows = shown()
        if rows:
            e.app.exit(result=rows[state["i"]]["_slug"])

    @kb.add("escape", eager=True)
    @kb.add("c-c", eager=True)
    def _cancel(e):
        e.app.exit(result=None)

    def listing():
        rows = shown()
        out = []
        if not rows:
            out.append(("class:dim", "  nothing matches · Backspace widens it\n"))
        tw = min(max((len(c["title"]) for c in rows), default=10), 28) + 2
        for i in range(state["top"], min(len(rows), state["top"] + VISIBLE)):
            c = rows[i]
            on = i == state["i"]
            _, s = A.status(c, st)
            glyph, gcls = {"ok": (G.ok, "ok"), "fail": (G.err, "err")}.get(s, (G.warn, "warn"))
            out += [("class:focus" if on else "class:field", f"{G.select if on else ' '} "),
                    (f"class:{gcls}", glyph + " "),
                    ("class:dim", f"{num.get(c['_slug'], '?'):>2}  "),
                    ("class:focus" if on else "class:field", A.clip(c["title"], tw - 2).ljust(tw)),
                    ("class:muted", A.clip(c.get("what", ""), 36) + "\n")]
        hidden = len(rows) - VISIBLE if len(rows) > VISIBLE else 0
        if hidden:
            out.append(("class:dim", f"  {G.fold} {len(rows)} match{G.sep}↑↓ scrolls\n"))
        out.append(("", "\n"))
        out += [("class:dim", "  type to filter · ↑↓ move · "), ("class:key", " Enter open "), ("class:dim", " · Esc quit")]
        return FormattedText(out)

    body = Frame(HSplit([query, Window(FormattedTextControl(listing), dont_extend_height=True)],
                        width=Dimension(max=S.DESIGN_WIDTH - 2)),
                 title=title, style="class:frame.border", width=S.DESIGN_WIDTH)
    body = VSplit([body, Window()])        # keep the frame at 80 columns in a wider terminal
    app = Application(layout=Layout(body, focused_element=query), key_bindings=kb, style=STYLE,
                      full_screen=False, erase_when_done=True)
    return await app.run_async()
