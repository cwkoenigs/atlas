"""Cards into ds_cli_design.browse: the filterable, framed picker from the design system."""
from __future__ import annotations

from ds_cli_design import picker as P

from . import core as A


async def browse(title: str, cards, st, num) -> str | None:
    """Returns the chosen card's slug, or None on Esc / Ctrl-C."""
    items = [P.Item(value=c["_slug"], label=c["title"], detail=c.get("what", ""),
                    outcome={"ok": "ok", "fail": "err"}.get(A.status(c, st)[1], "warn"),
                    number=num.get(c["_slug"]),
                    search=f"{A.host_name(c.get('host', ''))} {c.get('kind', '')}")
             for c in cards]
    return await P.browse(title, items)
