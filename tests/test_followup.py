"""Remaining independent acceptance gates; all data and processes are disposable."""
from .support import *
import io
import shlex
import signal
import threading
import time
from http.server import ThreadingHTTPServer
from atlas_cli.wiki import server as S, render as R, actions as X, views as V


class FollowupTests(InventoryTest):
    def wait_file(self, name):
        deadline = time.monotonic() + 4
        while not (self.root / name).exists():
            self.assertLess(time.monotonic(), deadline, name)
            time.sleep(.01)

    def test_form_referrer_policy_and_strict_origin(self):
        handler = object.__new__(S.Handler)
        headers = {}
        handler.command = 'HEAD'
        handler.send_response = lambda status: None
        handler.send_header = lambda k, v: headers.__setitem__(k, v)
        handler.end_headers = lambda: None
        handler._send(200, b'', 'text/html', nonce='fixture')
        self.assertEqual(headers['Referrer-Policy'], 'same-origin')
        from types import SimpleNamespace
        handler.server = SimpleNamespace(server_port=8788)
        handler.headers = {'Host': 'localhost:8788', 'Origin': 'null', 'Sec-Fetch-Site': 'same-origin'}
        statuses = []
        handler._plain = lambda status, text: statuses.append(status)
        handler.do_POST()
        self.assertEqual(statuses, [403])

    def test_stop_completed_identity_marker_without_pid_reap(self):
        meta = dict(app='atlas-wiki', version=S.VERSION, root=str(self.root), pid=12345,
                    port=8788, instance='fixture-instance')
        path = self.root / '.state/wiki-server.json'
        path.parent.mkdir()
        path.write_text(json.dumps({**meta, 'stopped': True}))
        with patch.object(S, 'health', return_value=meta), patch.object(S.os, 'kill'), \
             patch.object(S.time, 'sleep'):
            self.assertTrue(S.stop())

    def test_stop_rejects_foreign_marker_and_health_loss(self):
        meta = dict(app='atlas-wiki', root=str(self.root), pid=12345, port=8788, instance='current')
        path = self.root / '.state/wiki-server.json'
        path.parent.mkdir()
        path.write_text(json.dumps({**meta, 'instance': 'older', 'stopped': True}))
        with patch.object(S, 'health', return_value=meta), patch.object(S.os, 'kill'), \
             patch.object(S.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'draining'): S.stop()

    def test_shutdown_marker_only_after_drain_and_close(self):
        entered, release, exited = [threading.Event() for _ in range(3)]
        errors, instances = [], []
        def bind(srv): srv.server_port = srv.server_address[1]
        def serving(srv):
            instances.append(srv)
            with srv.mutation():
                entered.set()
                release.wait(3)
        def close(srv):
            metadata = json.loads((self.root / '.state/wiki-server.json').read_text())
            self.assertFalse(metadata.get('stopped', False))
            ThreadingHTTPServer.server_close(srv)
        def run():
            try: S.serve()
            except BaseException as ex: errors.append(ex)
            finally: exited.set()
        with patch.object(ThreadingHTTPServer, 'server_bind', bind), \
             patch.object(ThreadingHTTPServer, 'server_activate'), \
             patch.object(ThreadingHTTPServer, 'serve_forever', serving), \
             patch.object(S.WikiServer, 'server_close', close), patch.object(S.signal, 'signal'):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                before = json.loads((self.root / '.state/wiki-server.json').read_text())
                self.assertFalse(before.get('stopped', False))
            finally:
                release.set()
                worker.join(3)
            self.assertTrue(exited.is_set())
            self.assertFalse(errors)
        path = self.root / '.state/wiki-server.json'
        self.assertTrue(path.exists(), 'completion marker must survive an unreaped server')
        after = json.loads(path.read_text())
        self.assertTrue(after['stopped'])
        self.assertEqual(after['instance'], before['instance'])

    def test_move_claim_failure_rolls_back(self):
        c = self.card()
        source, raw = c['_path'], c['_raw']
        rename = A._rename_claim
        def fail(path, target, *args, **kwargs):
            if path == source: raise PermissionError('injected source denial')
            return rename(path, target, *args, **kwargs)
        with patch.object(A, '_rename_claim', fail):
            with self.assertRaises(PermissionError): A.retire(c, 'fixture')
        self.assertEqual(source.read_bytes(), raw.encode())
        self.assertFalse((self.root / 'retired/thing.md').exists())
        self.assertEqual(len(A.load()), 1)
        self.assertEqual(H.entries(self.root, c['id'])[-1]['text'], raw)

    def test_move_refuses_source_replaced_during_staging(self):
        c = self.card()
        source, original = c['_path'], c['_raw'].encode()
        atomic = A.atomic_write
        def replace_source(path, text):
            atomic(path, text)
            if path.name.startswith('.atlas-move-'):
                replacement = source.with_suffix('.replacement')
                replacement.write_bytes(original)
                os.replace(replacement, source)
        with patch.object(A, 'atomic_write', replace_source):
            with self.assertRaises(A.Conflict): A.retire(c)
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse((self.root / 'retired/thing.md').exists())

    def interrupt_move(self, after_claim=False, point='claim'):
        c = self.card()
        code = '''from atlas_cli import core as A
import pathlib, os
source = A.ROOT/'cards/thing.md'
rename = A._rename_claim
def interrupt(path, target, *args, **kwargs):
    if path == source:
        if AFTER: rename(path, target, *args, **kwargs)
        os._exit(73)
    return rename(path, target, *args, **kwargs)
if POINT == 'claim': A._rename_claim = interrupt
if POINT == 'journal':
    atomic = A.atomic_write
    def stop_after_journal(path, text):
        atomic(path, text)
        if path.name == 'move.json': os._exit(73)
    A.atomic_write = stop_after_journal
elif POINT == 'history':
    A._clear_move = lambda *args: os._exit(73)
A.retire(A.load()[0], 'interrupted fixture')
'''.replace('AFTER', repr(after_claim)).replace('POINT', repr(point))
        p = self.process(code)
        out, err = p.communicate(timeout=5)
        self.assertEqual(p.returncode, 73, out + err)
        self.assertEqual((self.root / 'retired/thing.md').exists(), point != 'journal')
        return c

    def test_move_interruption_before_destination(self):
        c = self.interrupt_move(point='journal')
        self.assertEqual(A.find(c['id'])['_folder'], 'retired')
        self.assertEqual(H.entries(self.root, c['id'])[0]['text'], c['_raw'])

    def test_move_interruption_after_history_is_idempotent(self):
        c = self.interrupt_move(after_claim=True, point='history')
        before = H.entries(self.root, c['id'])
        self.assertEqual(A.find(c['id'])['_folder'], 'retired')
        self.assertEqual(H.entries(self.root, c['id']), before)

    def test_move_interruption_recovered_on_inventory_read(self):
        for after_claim in (False, True):
            with self.subTest(after_claim=after_claim):
                c = self.interrupt_move(after_claim)
                # A fresh process uses ordinary find/load, never a repair command.
                p = self.process("from atlas_cli import core as A; c=A.find('a-000001'); assert c['_folder']=='retired'")
                self.finish(p)
                cards = A.load()
                self.assertEqual(len(cards), 1)
                self.assertEqual(cards[0]['retired_reason'], 'interrupted fixture')
                history = H.entries(self.root, c['id'])
                self.assertEqual(history[0]['text'], c['_raw'])
                self.assertEqual(history[-1]['text'], cards[0]['_raw'])
                count = len(history)
                A.load()
                self.assertEqual(len(H.entries(self.root, c['id'])), count)
                cards[0]['_path'].unlink()

    def assert_recovery_refuses_changed_file(self, which, replace_inode=True):
        c = self.interrupt_move()
        source, dest = c['_path'], self.root / 'retired/thing.md'
        path = source if which == 'source' else dest
        if replace_inode:
            # Same bytes with a replaced inode are also an identity conflict.
            replacement = path.with_suffix('.replacement')
            replacement.write_bytes(path.read_bytes())
            os.replace(replacement, path)
        else:
            path.write_bytes(path.read_bytes().replace(b'fake', b'new owner'))
        before = {p: p.read_bytes() for p in (source, dest)}
        with self.assertRaises(A.Conflict): A.load()
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_move_recovery_refuses_replaced_source(self):
        self.assert_recovery_refuses_changed_file('source')

    def test_move_recovery_refuses_replaced_destination(self):
        self.assert_recovery_refuses_changed_file('destination')

    def test_move_recovery_refuses_edited_source(self):
        self.assert_recovery_refuses_changed_file('source', False)

    def test_move_recovery_refuses_edited_destination(self):
        self.assert_recovery_refuses_changed_file('destination', False)

    def test_move_recovery_refuses_escaping_journal(self):
        self.interrupt_move()
        path = self.root / '.state/move.json'
        j = json.loads(path.read_text())
        j['source'] = '../unrelated.md'
        unrelated = self.root / 'unrelated.md'
        unrelated.write_text('untouched')
        path.write_text(json.dumps(j))
        with self.assertRaises(A.Conflict): A.load()
        self.assertEqual(unrelated.read_text(), 'untouched')

    def test_move_recovery_refuses_partial_journal(self):
        c = self.card()
        path = self.root / '.state/move.json'
        path.parent.mkdir()
        path.write_text('{"source":')
        with self.assertRaises(A.Conflict): A.load()
        self.assertEqual(c['_path'].read_bytes(), c['_raw'].encode())
        self.assertEqual(path.read_text(), '{"source":')

    def test_check_sigint_cancels_descendants(self):
        child = "import pathlib,time; pathlib.Path('started').touch(); time.sleep(.7); pathlib.Path('escaped').touch()"
        c = self.card(check=shlex.join([sys.executable, '-c', child]))
        p = self.process("from atlas_cli import core as A; A.CFG['check_timeout']=8; A.run_checks(A.load())")
        self.wait_file('started')
        os.kill(p.pid, signal.SIGINT)
        out, err = p.communicate(timeout=4)
        self.assertNotEqual(p.returncode, 0, out + err)
        self.assertIn('KeyboardInterrupt', err)
        time.sleep(.85)
        self.assertFalse((self.root / 'escaped').exists(), 'detached check survived cancellation')
        self.assertFalse(A.STATE.exists(), 'cancelled checks committed results')

    def test_check_communication_failure_cancels_descendants(self):
        child = "import pathlib,time; pathlib.Path('started').touch(); time.sleep(.7); pathlib.Path('escaped').touch()"
        c = self.card(check=shlex.join([sys.executable, '-c', child]))
        p = self.process('''from atlas_cli import core as A
import subprocess,time
popen = subprocess.Popen
processes = []
error = OSError('injected pipe failure')
def failing_popen(*args, **kwargs):
    p = popen(*args, **kwargs)
    processes.append(p)
    deadline = time.monotonic()+4
    while not (A.ROOT/'started').exists():
        assert time.monotonic()<deadline
        time.sleep(.01)
    p.communicate = lambda **kw: (_ for _ in ()).throw(error)
    return p
A.subprocess.Popen = failing_popen
try:
    A.run_checks(A.load())
except OSError as ex:
    assert ex is error, repr(ex)
else:
    raise AssertionError('communication failure swallowed')
assert processes[0].returncode is not None, 'direct child was not reaped'
processes[0].stdout.close()
processes[0].stderr.close()
''')
        self.finish(p)
        time.sleep(.85)
        self.assertFalse((self.root / 'escaped').exists())

    def test_crlf_revision_render(self):
        c = self.card()
        raw = A.dump({**c, 'what': 'Historical description', '_body': 'Historical body\n'}).replace('\n', '\r\n')
        H.record(self.root, c['id'], raw, 'old CRLF', 'wiki')
        snap = R.Snap()
        view = V.revision(snap, c, 'h1')
        self.assertIn('Historical description', view[1])
        self.assertIn('Historical body', view[1])
        self.assertNotIn('id: a-000001', view[1])
        self.assertEqual(R.parse_text(raw, c)['_body'], 'Historical body\r\n')

    def test_crlf_revision_restore_exact_bytes(self):
        c = self.card()
        raw = A.dump({**c, 'what': 'Historical description', '_body': 'Historical body\n'}).replace('\n', '\r\n')
        H.record(self.root, c['id'], raw, 'old CRLF', 'wiki')
        snap = R.Snap()
        with patch.object(A, 'rebuild'):
            result = X.restore(snap, c, {'key': 'h1'})
        self.assertEqual(result[0], 'redirect')
        self.assertEqual(c['_path'].read_bytes(), raw.encode())
        history = H.entries(self.root, c['id'])
        self.assertEqual(history[-2]['text'], snap.cards[0]['_raw'])
        self.assertEqual(history[-1]['text'], raw)
