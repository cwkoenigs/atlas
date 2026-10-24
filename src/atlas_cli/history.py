"""Every version of every card, kept on this Mac in .state/history (ignored by git, so personal cards stay here).

One JSON-lines file per card id. Each entry is the card file's full text after a change, with when, who
(wiki, cli, scan, outside, earlier) and a one-line summary. Diffs are computed between entries.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

BY = {"wiki": "edited in the wiki", "cli": "atlas command", "scan": "atlas scan",
      "outside": "changed outside atlas", "earlier": "before atlas kept history", "git": "git commit"}


def _file(root: pathlib.Path, cid: str) -> pathlib.Path:
    return root / ".state" / "history" / f"{cid}.jsonl"


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def entries(root, cid) -> list[dict]:
    """Oldest first. Each entry gets `n`, its 1-based position, which is its revision number."""
    p = _file(root, cid)
    if not cid or not p.is_file():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        entry["n"] = len(out) + 1
        out.append(entry)
    return out


def record(root, cid, text, summary, by, at=None, force=False):
    """Append a version. Skipped when the text is unchanged, unless force (a move, a confirmation)."""
    if not cid:
        return None
    old = entries(root, cid)
    if old and old[-1]["text"] == text and not force:
        return None
    entry = {"at": at or now(), "by": by, "summary": summary, "text": text}
    p = _file(root, cid)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def mtime(path) -> str:
    return dt.datetime.fromtimestamp(pathlib.Path(path).stat().st_mtime).isoformat(timespec="seconds")


def ensure_base(root, cid, path):
    """Before the first recorded change, keep the version that was there."""
    path = pathlib.Path(path)
    if cid and path.is_file() and not entries(root, cid):
        record(root, cid, path.read_text(), "", "earlier", at=mtime(path))


def sync(root, cards):
    """Catch changes made outside atlas (an editor, an agent's patch) so history and recent changes see them."""
    for c in cards:
        cid, path = c.get("id"), c["_path"]
        if not cid or not path.is_file():
            continue
        old = entries(root, cid)
        text = path.read_text()
        if not old:
            record(root, cid, text, "", "earlier", at=mtime(path))
        elif old[-1]["text"] != text:
            record(root, cid, text, "changed outside atlas (an editor or an agent)", "outside", at=mtime(path))
