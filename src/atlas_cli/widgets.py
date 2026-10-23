"""Copied from the ds-next terminal design system v1 (final/code/widgets.py). One change: frames stay
at their width in a wider terminal (VSplit with a filler); upstream they overshoot.

Two inline widgets drawn with the ui_style roles: a picker and a one-screen form.

Both draw below the prompt (not full screen), erase themselves when done, and return a value,
or None when the user presses Esc or Ctrl-C. A frame means "needs you".
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from . import ui_style as S
from .ui_style import G, LABEL_W

STYLE = Style.from_dict(S.pt_style())


def _keys(*parts: tuple[str, str]) -> list[tuple[str, str]]:
    """Key line: dim text with the one submit key as a band."""
    return [("class:dim", "  ")] + [(f"class:{cls}", txt) for cls, txt in parts]


async def pick(title: str, options: list[tuple[str, str, str]]) -> str | None:
    """options: (value, label, description). ↑/↓ or a digit to move, Enter to choose."""
    state = {"i": 0}
    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _up(e):
        state["i"] = (state["i"] - 1) % len(options)

    @kb.add("down")
    @kb.add("j")
    @kb.add("tab")
    def _down(e):
        state["i"] = (state["i"] + 1) % len(options)

    @kb.add("enter")
    def _enter(e):
        e.app.exit(result=options[state["i"]][0])

    @kb.add("escape")
    @kb.add("c-c")
    def _cancel(e):
        e.app.exit(result=None)

    for n in range(1, min(len(options), 9) + 1):
        @kb.add(str(n))
        def _num(e, n=n):
            state["i"] = n - 1
            e.app.exit(result=options[n - 1][0])

    def text():
        out = []
        for i, (_, label, desc) in enumerate(options):
            on = i == state["i"]
            out += [("class:focus" if on else "class:field", f" {G.select if on else ' '} {i + 1}. {label}"),
                    ("class:muted", f"  {desc}\n")]
        out.append(("", "\n"))
        out += _keys(("dim", "↑↓ move · "), ("key", " Enter choose "), ("dim", " · Esc cancel"))
        return FormattedText(out)

    body = Frame(Window(FormattedTextControl(text), dont_extend_height=True), title=title, style="class:frame.border")
    app = Application(layout=Layout(body), key_bindings=kb, style=STYLE, full_screen=False, erase_when_done=True)
    return await app.run_async()


@dataclass
class Field:
    key: str
    label: str
    value: str = ""
    hint: str = ""
    required: bool = False
    choices: list[tuple[str, str]] | None = None
    example: str = ""
    normalize: Callable[[str], str] | None = None
    check: Callable[[str], str | None] | None = None


async def form(title: str, fields: list[Field], footer: Callable[[dict[str, str]], str],
               validate: Callable[[dict[str, str]], tuple[str, str] | None],
               width: int = S.DESIGN_WIDTH) -> dict[str, str] | None:
    """Every field on one screen, already filled with a suggestion, inside a square frame.
    Tab/↓ and Shift-Tab/↑ move, Enter submits from any field. Labels sit on the LABEL_W grid."""
    chosen = {f.key: max(0, next((i for i, (v, _) in enumerate(f.choices) if v == f.value), 0))
              for f in fields if f.choices}

    def choice_text(f: Field):
        def get():
            on = get_app().layout.has_focus(areas[f.key])
            i = chosen[f.key]
            return FormattedText([("class:strong" if on else "class:field", f"‹ {f.choices[i][1]} ›"),
                                  ("class:dim", f"  {i + 1}/{len(f.choices)}" if on else "")])
        return get

    areas = {}
    for f in fields:
        if f.choices:
            areas[f.key] = Window(FormattedTextControl(choice_text(f), focusable=True), height=1, dont_extend_height=True)
        else:
            areas[f.key] = TextArea(text=f.value, multiline=False, wrap_lines=False, style="class:field")
    order = [areas[f.key] for f in fields]
    error = {"msg": ""}

    def normalizer(f: Field):
        def on_change(buf):
            fixed = f.normalize(buf.text)
            if fixed != buf.text:
                buf.text = fixed
                buf.cursor_position = len(fixed)
        return on_change

    for f in fields:
        if f.normalize and not f.choices:
            areas[f.key].buffer.on_text_changed += normalizer(f)

    def values() -> dict[str, str]:
        return {f.key: (f.choices[chosen[f.key]][0] if f.choices else areas[f.key].text.strip()) for f in fields}

    def focused_choice() -> Field | None:
        return next((f for f in fields if f.choices and get_app().layout.has_focus(areas[f.key])), None)

    def label(f: Field):
        def get():
            on = get_app().layout.has_focus(areas[f.key])
            mark = "*" if f.required else " "
            return FormattedText([("class:focus" if on else "class:label",
                                   f"{G.select if on else ' '} {f.label:<{LABEL_W}}{mark} ")])
        return Window(FormattedTextControl(get), width=LABEL_W + 4, dont_extend_width=True)

    def hint():
        focused = next((f for f in fields if get_app().layout.has_focus(areas[f.key])), None)
        v = values()
        line = ""
        if focused:
            bits = []
            if focused.example and not v[focused.key]:
                bits.append(f"e.g. {focused.example}")
            if focused.hint:
                bits.append(focused.hint)
            line = " · ".join(bits)
        parts = [("class:dim", f"  {line}\n" if line else "\n")]
        parts.append(("class:accent", f"  {footer(v)}\n"))
        live = focused.check(v[focused.key]) if focused and focused.check and v[focused.key] else None
        if live:
            parts.append(("class:error", f"  {G.err} {live}\n"))
        elif error["msg"]:
            parts.append(("class:error", f"  {G.err} {error['msg']}\n"))
        else:
            parts.append(("", "\n"))
        keys = "←/→ change · " if focused_choice() else ""
        parts += _keys(("dim", f"{keys}Tab next · ↑ back · "), ("key", " Enter submit "), ("dim", " · Esc cancel"))
        return FormattedText(parts)

    kb = KeyBindings()

    def move(step: int):
        i = next((n for n, a in enumerate(order) if get_app().layout.has_focus(a)), 0)
        get_app().layout.focus(order[(i + step) % len(order)])

    @kb.add("tab")
    @kb.add("down")
    def _next(e):
        move(1)

    @kb.add("s-tab")
    @kb.add("up")
    def _prev(e):
        move(-1)

    def cycle(step: int):
        f = focused_choice()
        if f is not None:
            chosen[f.key] = (chosen[f.key] + step) % len(f.choices)

    @kb.add("right")
    def _right(e):
        if focused_choice() is not None:
            cycle(1)
        else:
            e.app.current_buffer.cursor_right()

    @kb.add(" ")
    def _space(e):
        if focused_choice() is not None:
            cycle(1)
        else:
            e.app.current_buffer.insert_text(" ")

    @kb.add("left")
    def _left(e):
        if focused_choice() is not None:
            cycle(-1)
        else:
            e.app.current_buffer.cursor_left()

    @kb.add("enter")
    def _submit(e):
        v = values()
        missing = next((f for f in fields if f.required and not v[f.key]), None)
        broken = next(((f.key, f.check(v[f.key])) for f in fields if f.check and v[f.key] and f.check(v[f.key])), None)
        problem = (missing.key, f"{missing.label} is required") if missing else broken or validate(v)
        if problem:
            error["msg"] = problem[1]
            e.app.layout.focus(areas[problem[0]])
            return
        e.app.exit(result=v)

    @kb.add("escape")
    @kb.add("c-c")
    def _cancel(e):
        e.app.exit(result=None)

    rows = [VSplit([label(f), areas[f.key]]) for f in fields]
    rows.append(Window(FormattedTextControl(hint), dont_extend_height=True))
    body = VSplit([Frame(HSplit(rows, width=Dimension(max=width - 2)), title=title, style="class:frame.border",
                         width=width), Window()])
    app = Application(layout=Layout(body, focused_element=order[0]), key_bindings=kb, style=STYLE,
                      full_screen=False, erase_when_done=True)
    return await app.run_async()
