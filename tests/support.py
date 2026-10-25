"""Tests only ever import Atlas with a disposable inventory selected."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

_BOOT = tempfile.TemporaryDirectory(prefix="atlas-import-", dir=os.environ.get("TMPDIR", "/tmp"))
os.environ["ATLAS_DIR"] = _BOOT.name
pathlib.Path(_BOOT.name, "atlas.json").write_text('{"hosts":{"mac":"Mac"}}')
from atlas_cli import core as A, history as H

class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="atlas-test-", dir=os.environ.get("TMPDIR", "/tmp"))
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        cfg = {"hosts": {"mac": "Mac"}, "check_timeout": 1, "wiki_port": 8788}
        (self.root / "atlas.json").write_text(json.dumps(cfg))
        for folder in ("cards", "inbox", "templates"):
            (self.root / folder).mkdir()
        (self.root / "templates/card.md").write_text('---\nid: a-000000\ntitle: Template\nlinks: []\nnotes: []\n---\nBody\n')
        for name, value in (("ROOT", self.root), ("STATE", self.root / ".state/checks.json"), ("CFG", cfg), ("HOME", self.root)):
            p = patch.object(A, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.dict(os.environ, {"ATLAS_DIR": str(self.root)})
        p.start()
        self.addCleanup(p.stop)

    def card(self, slug="thing", cid="a-000001", folder="cards", personal=False, **fields):
        path = self.root / folder / ("personal" if personal else "") / (slug + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        c = dict(id=cid, title=slug.title(), kind="folder", host="mac", where="fake", what="fake",
                 why="fake", source="fake", check="", links=[], notes=[], _body="Body\n")
        c.update(fields)
        path.write_text(A.dump(c))
        return A.parse(path)

    def process(self, code, *args):
        process = subprocess.Popen([sys.executable, "-c", "from atlas_cli import core as _A; _A.HOME = _A.ROOT\n" + code, *map(str, args)],
                                   env={**os.environ, "ATLAS_DIR": str(self.root)}, start_new_session=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.cleanup_process, process)
        return process

    def cleanup_process(self, process):
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=3)

    def finish(self, p):
        out, err = p.communicate(timeout=15)
        self.assertEqual(p.returncode, 0, out + err)
        return out
