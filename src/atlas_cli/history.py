"""Every version of every card, kept on this Mac in .state/history (ignored by git, so personal cards stay here).

One JSON-lines file per card id. Each entry is the card file's full text after a change, with when, who
(wiki, cli, scan, outside, earlier) and a one-line summary. Diffs are computed between entries.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import os
import tempfile
from functools import wraps
from .storage import locked, atomic_write, read_text

BY = {"wiki": "edited in the wiki", "cli": "atlas command", "scan": "atlas scan",
      "outside": "changed outside atlas", "earlier": "before atlas kept history", "git": "git commit"}


def transaction(fn):
    @wraps(fn)
    def run(root, *args, **kwargs):
        with locked(root):
            return fn(root, *args, **kwargs)
    return run


def _file(root: pathlib.Path, cid: str) -> pathlib.Path:
    if not isinstance(cid, str) or not re.fullmatch(r"a-[0-9a-f]{6}", cid):
        raise ValueError("History card ID must look like a-1b2c3d.")
    directory = pathlib.Path(root).resolve() / ".state" / "history"
    path = directory / f"{cid}.jsonl"
    if not path.resolve().is_relative_to(directory):
        raise ValueError("History path escapes .state/history.")
    return path


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _read(path):
    data = path.read_bytes() if path.is_file() else b""
    out, good, tail = [], b"", b""
    lines = data.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if not line.strip():
            good += line
            continue
        try:
            entry = json.loads(line)
        except (ValueError, UnicodeDecodeError) as ex:
            if i == len(lines) - 1 and not line.endswith(b"\n"):
                tail = line
                break
            raise ValueError(f"Corrupt history {path.name}, line {i+1}: {ex}") from ex
        if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) for k in ("at", "by", "summary", "text")):
            raise ValueError(f"Corrupt history {path.name}, line {i+1}: invalid entry fields")
        entry["n"] = len(out) + 1
        out.append(entry)
        good += line.rstrip(b"\r\n") + b"\n"
    return out, good, tail


@transaction
def entries(root, cid) -> list[dict]:
    """Oldest first; tolerate only an incomplete final crash fragment, never interior corruption."""
    return _read(_file(root, cid))[0] if cid else []


@transaction
def record(root, cid, text, summary, by, at=None, force=False):
    """Preserve valid tail entries and quarantine incomplete crash fragments before replacement."""
    if not cid:
        return None
    if not all(isinstance(value, str) for value in (text, summary, by, at or now())):
        raise ValueError("History fields must be text strings.")
    p = _file(root, cid)
    old, good, tail = _read(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    if tail:
        fd, name = tempfile.mkstemp(prefix=p.name + ".tail-", dir=p.parent)
        with os.fdopen(fd, "wb") as f:
            f.write(tail)
            f.flush()
            os.fsync(f.fileno())
    unchanged = old and old[-1]["text"] == text and not force
    entry = {"at": at or now(), "by": by, "summary": summary, "text": text}
    data = good.decode("utf-8")
    if not unchanged:
        data += json.dumps(entry, ensure_ascii=False) + "\n"
    atomic_write(p, data)
    return None if unchanged else entry


def mtime(path) -> str:
    return dt.datetime.fromtimestamp(pathlib.Path(path).stat().st_mtime).isoformat(timespec="seconds")


@transaction
def ensure_base(root, cid, path):
    """Preserve the exact on-disk preimage, including edits made outside Atlas."""
    path = pathlib.Path(path)
    if cid and path.is_file():
        old = entries(root, cid)
        text = read_text(path)
        if not old or old[-1]["text"] != text:
            record(root, cid, text, "changed outside atlas" if old else "", "outside" if old else "earlier", at=mtime(path))


@transaction
def sync(root, cards):
    """Catch changes made outside atlas (an editor, an agent's patch) so history and recent changes see them."""
    for c in cards:
        cid, path = c.get("id"), c["_path"]
        if not cid or not path.is_file():
            continue
        old = entries(root, cid)
        text = read_text(path)
        if not old:
            record(root, cid, text, "", "earlier", at=mtime(path))
        elif old[-1]["text"] != text:
            record(root, cid, text, "changed outside atlas (an editor or an agent)", "outside", at=mtime(path))
