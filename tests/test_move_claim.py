"""External editor saves interleaved with the durable move/removal boundaries."""
from .support import *


class MoveClaimTests(InventoryTest):
    def atomic_editor(self, path, data):
        p = self.process('''import os,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.editor-save')
q.write_bytes(bytes.fromhex(sys.argv[2])); os.replace(q,p)
''', path, data.hex())
        self.finish(p)

    def claims(self, data):
        return [p for p in self.root.rglob('*') if p.is_file() and
                '.atlas-claim-' in str(p) and p.read_bytes() == data]

    def interrupted(self):
        c = self.card()
        p = self.process('''import os
from atlas_cli import core as A
c=A.load()[0]; atomic=A.atomic_write
def stop(path,text):
    atomic(path,text)
    if path.name=='move.json': os._exit(73)
A.atomic_write=stop
A.retire(c)
''')
        out, err = p.communicate(timeout=5)
        self.assertEqual(p.returncode, 73, out + err)
        return c

    def after_publication(self, recovery):
        c = self.interrupted() if recovery else self.card()
        source, dest = c['_path'], self.root / 'retired/thing.md'
        data = A.dump({**c, 'what': 'external edit', '_body': 'DO NOT DELETE\n'}).encode()
        link = os.link
        def replace(src, dst, *args, **kwargs):
            result = link(src, dst, *args, **kwargs)
            if pathlib.Path(dst) == dest:
                self.atomic_editor(source, data)
            return result
        with patch.object(A.os, 'link', replace):
            with self.assertRaises(A.Conflict):
                A.load() if recovery else A.retire(c)
        self.assertEqual(source.read_bytes(), data)
        self.assertTrue(self.claims(data), 'claimed edit must remain durably recoverable')
        self.assertFalse(dest.exists())
        self.assertFalse(any('DO NOT DELETE' in h['text'] for h in H.entries(self.root, c['id'])))

    def test_atomic_editor_after_destination_publication(self):
        self.after_publication(False)

    def test_recovery_atomic_editor_after_destination_publication(self):
        self.after_publication(True)

    def at_claim(self, when, create_original=False):
        c = self.card()
        source = c['_path']
        data = A.dump({**c, '_body': 'CLAIM EDIT\n'}).encode()
        rename = A._rename_claim
        def replace(src, dst, *args, **kwargs):
            if pathlib.Path(src) == source and when == 'before':
                self.atomic_editor(source, data)
            result = rename(src, dst, *args, **kwargs)
            if pathlib.Path(src) == source and when == 'after':
                self.atomic_editor(pathlib.Path(dst), data)
                if create_original:
                    self.atomic_editor(source, b'NEW ORIGINAL MUST SURVIVE\n')
            return result
        with patch.object(A, '_rename_claim', replace):
            with self.assertRaises(A.Conflict): A.retire(c)
        self.assertEqual(source.read_bytes(), b'NEW ORIGINAL MUST SURVIVE\n' if create_original else data)
        self.assertTrue(self.claims(data))
        self.assertFalse((self.root / 'retired/thing.md').exists())

    def test_source_replaced_before_claim(self):
        self.at_claim('before')

    def test_claim_replaced_after_rename(self):
        self.at_claim('after')

    def test_rollback_never_overwrites_new_original(self):
        self.at_claim('after', True)

    def test_original_created_after_claim_is_preserved(self):
        c = self.card()
        source = c['_path']
        rename = A._rename_claim
        def create(src, dst, *args, **kwargs):
            result = rename(src, dst, *args, **kwargs)
            if pathlib.Path(src) == source:
                self.atomic_editor(source, b'NEW ORIGINAL\n')
            return result
        with patch.object(A, '_rename_claim', create):
            with self.assertRaises(A.Conflict): A.retire(c)
        self.assertEqual(source.read_bytes(), b'NEW ORIGINAL\n')
        self.assertTrue(self.claims(c['_raw'].encode()))
        self.assertFalse((self.root / 'retired/thing.md').exists())

    def test_rollback_claims_replaced_destination_without_deleting_it(self):
        c = self.card()
        source, dest = c['_path'], self.root / 'retired/thing.md'
        rename = A._rename_claim
        def interleave(src, dst, *args, **kwargs):
            if pathlib.Path(src) == source:
                raise PermissionError('claim denied')
            if pathlib.Path(src) == dest:
                self.atomic_editor(dest, b'EXTERNAL DESTINATION\n')
            return rename(src, dst, *args, **kwargs)
        with patch.object(A, '_rename_claim', interleave):
            with self.assertRaises(A.Conflict): A.retire(c)
        self.assertEqual(source.read_bytes(), c['_raw'].encode())
        self.assertEqual(dest.read_bytes(), b'EXTERNAL DESTINATION\n')
        self.assertTrue(self.claims(b'EXTERNAL DESTINATION\n'))
        with self.assertRaises(A.Conflict): A.load()

    def test_open_fd_edit_after_claim_validation_keeps_inode(self):
        c = self.card()
        source = c['_path']
        source.chmod(0o640)
        H.ensure_base(self.root, c['id'], source)
        record = H.record
        with source.open('r+b') as editor:
            def late_edit(*args, **kwargs):
                editor.seek(0); editor.write(b'LATE OPEN FD EDIT\n'); editor.truncate()
                editor.flush(); os.fsync(editor.fileno())
                return record(*args, **kwargs)
            with patch.object(H, 'record', late_edit): A.retire(c)
        backups = self.claims(b'LATE OPEN FD EDIT\n')
        self.assertTrue(backups)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o640)
        self.assertFalse(source.exists())

    def test_crash_after_claim_before_history_recovers(self):
        c = self.card()
        p = self.process('''import os
from atlas_cli import core as A
c=A.load()[0]
A.H.ensure_base(A.ROOT,c['id'],c['_path'])
A.H.record=lambda *args,**kwargs: os._exit(73)
A.retire(c)
''')
        out, err = p.communicate(timeout=5)
        self.assertEqual(p.returncode, 73, out + err)
        self.assertFalse(c['_path'].exists())
        self.assertTrue(self.claims(c['_raw'].encode()))
        self.finish(self.process("from atlas_cli import core as A; assert A.find('a-000001')['_folder']=='retired'"))
        entries = H.entries(self.root, c['id'])
        self.assertEqual(entries[0]['text'], c['_raw'])
        self.assertEqual(entries[-1]['text'], A.load()[0]['_raw'])
        A.load()
        self.assertEqual(H.entries(self.root, c['id']), entries)

    def test_claim_path_cannot_escape_inventory(self):
        c = self.interrupted()
        path = self.root / '.state/move.json'
        j = json.loads(path.read_text()); j['source_claim'] = '../outside'
        path.write_text(json.dumps(j))
        with self.assertRaises(A.Conflict): A.load()
        self.assertEqual(c['_path'].read_bytes(), c['_raw'].encode())

    def test_claim_occupied_at_rename_is_never_overwritten(self):
        c = self.card()
        source = c['_path']
        rename = A._rename_claim
        occupied = []
        def occupy(src, dst, *args, **kwargs):
            if pathlib.Path(src) == source:
                self.atomic_editor(pathlib.Path(dst), b'UNKNOWN CLAIM\n')
                occupied.append(pathlib.Path(dst))
            return rename(src, dst, *args, **kwargs)
        with patch.object(A, '_rename_claim', occupy):
            with self.assertRaises(A.Conflict): A.retire(c)
        self.assertEqual(occupied[0].read_bytes(), b'UNKNOWN CLAIM\n')
        self.assertEqual(source.read_bytes(), c['_raw'].encode())

    def test_recovery_retains_changed_claim_for_reconciliation(self):
        c = self.card()
        p = self.process('''import os
from atlas_cli import core as A
c=A.load()[0]; rename=A._rename_claim
def crash(src,dst):
    rename(src,dst)
    if src==c['_path']: os._exit(73)
A._rename_claim=crash
A.retire(c)
''')
        out, err = p.communicate(timeout=5)
        self.assertEqual(p.returncode, 73, out + err)
        j = json.loads((self.root / '.state/move.json').read_text())
        claim = self.root / j['source_claim']
        self.atomic_editor(claim, b'CHANGED CLAIM\n')
        before = {p: p.read_bytes() for p in (claim, self.root / j['dest'], self.root / j['stage'])}
        with self.assertRaises(A.Conflict): A.load()
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertFalse(c['_path'].exists())

    def test_reader_waits_while_source_is_claimed(self):
        import threading
        c = self.card()
        entered, release, done = [threading.Event() for _ in range(3)]
        rename, cards, errors = A._rename_claim, [], []
        def hold(src, dst):
            rename(src, dst)
            if src == c['_path']:
                entered.set()
                if not release.wait(3): raise RuntimeError('fixture timeout')
        def writer():
            try: A.retire(c)
            except BaseException as ex: errors.append(ex)
        def reader():
            try: cards.extend(A.load())
            except BaseException as ex: errors.append(ex)
            finally: done.set()
        with patch.object(A, '_rename_claim', hold):
            w = threading.Thread(target=writer); w.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertFalse(c['_path'].exists())
                r = threading.Thread(target=reader); r.start()
                self.assertFalse(done.wait(.15))
            finally:
                release.set(); w.join(3)
                if 'r' in locals(): r.join(3)
        self.assertEqual(errors, [])
        self.assertTrue(done.is_set())
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['_folder'], 'retired')
