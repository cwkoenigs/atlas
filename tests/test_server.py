"""Real HTTP handler sockets without TCP bind, which the execution sandbox denies."""
from .support import *
import concurrent.futures
import signal
import socket
import threading
import time
from http.server import ThreadingHTTPServer
from atlas_cli.wiki import server as S

class ServerTests(InventoryTest):
    def test_12_shutdown_drains_mutation_ignores_idle(self):
        c = self.card()
        serving, stopped, ready, release, exited = [threading.Event() for _ in range(5)]
        servers, signals, errors = [], [], []
        def serve_forever(srv):
            servers.append(srv)
            serving.set()
            stopped.wait(4)
        def bind(srv):
            srv.server_port = srv.server_address[1]
        def mutation(handler, form):
            ready.set()
            release.wait(4)
            A.confirm(A.load()[0], by='wiki')
            handler._plain(200, 'saved')
        def serve():
            try: S.serve()
            except BaseException as ex: errors.append(ex)
            finally: exited.set()
        with patch.object(ThreadingHTTPServer, 'server_bind', bind), \
             patch.object(ThreadingHTTPServer, 'server_activate'), \
             patch.object(ThreadingHTTPServer, 'serve_forever', serve_forever), \
             patch.object(ThreadingHTTPServer, 'shutdown', lambda srv: stopped.set()), \
             patch.object(S.signal, 'signal', lambda sig, fn: signals.append(fn)), \
             patch.object(S.Handler, '_post', mutation):
            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            self.assertTrue(serving.wait(2), errors)
            srv = servers[0]
            pairs = [socket.socketpair() for _ in range(2)]
            for a, b in pairs:
                self.addCleanup(a.close)
                self.addCleanup(b.close)
                srv.process_request(a, ('127.0.0.1', 1))
            client = pairs[0][1]
            body = 'token='+S.TOKEN
            client.sendall((f'POST /wiki/thing/do HTTP/1.0\r\nHost: localhost:{srv.server_port}\r\nContent-Length: {len(body)}\r\n\r\n'+body).encode())
            self.assertTrue(ready.wait(2))
            signals[0](signal.SIGTERM, None)
            try:
                self.assertFalse(exited.wait(.2), 'server exited with an unfinished mutation')
            finally:
                release.set()
                worker.join(3)
            self.assertTrue(exited.is_set(), 'idle request prevented shutdown')
            self.assertFalse(errors)
        self.assertEqual(A.parse(c['_path'])['confirmed'], A.TODAY.isoformat())
        self.assertEqual(H.entries(self.root, c['id'])[-1]['text'], c['_path'].read_text())

    def test_17_bound_host_and_origin(self):
        from types import SimpleNamespace
        from contextlib import nullcontext
        import io
        handler = S.Handler.__new__(S.Handler)
        handler.server = SimpleNamespace(server_port=8788, mutation=nullcontext)
        handler.headers = {'Host': 'localhost:8788', 'Origin': 'http://localhost:8788'}
        A.CFG['wiki_port'] = 9999
        self.assertTrue(handler._host_ok())
        body = ('token='+S.TOKEN).encode()
        handler.headers['Content-Length'] = str(len(body))
        handler.rfile = io.BytesIO(body)
        called = []
        handler._post = lambda form: called.append(form)
        handler._plain = lambda status, text: self.fail(f'{status}: {text}')
        handler.do_POST()
        self.assertEqual(len(called), 1)
        handler.headers['Host'] = 'localhost:9999'
        self.assertFalse(handler._host_ok())

    def test_17_discover_old_port_restart_and_stop(self):
        from unittest.mock import Mock
        import io
        meta = dict(app='atlas-wiki', version=S.VERSION, root=str(self.root), pid=12345, port=8788)
        directory = self.root / '.state'
        directory.mkdir()
        (directory / 'wiki-server.json').write_text(json.dumps(meta))
        A.CFG['wiki_port'] = 9999
        def urlopen(url, timeout):
            if ':8788/' not in url: raise OSError('not bound')
            return io.BytesIO(json.dumps(meta).encode())
        with patch.object(S.urllib.request, 'urlopen', urlopen):
            self.assertEqual(S.health()['port'], 8788)
            with patch.object(S, 'stop') as stop, patch.object(S, 'start') as start:
                S.ensure()
                stop.assert_called_once()
                start.assert_called_once()
            calls = []
            def kill(pid, sig):
                calls.append((pid,sig))
                if sig == 0: raise ProcessLookupError()
            with patch.object(S.os, 'kill', kill), patch.object(S.time, 'sleep'):
                self.assertTrue(S.stop())
            self.assertIn((12345, signal.SIGTERM), calls)

    def test_12_shutdown_drains_get_history_sync(self):
        ready, release, drained = [threading.Event() for _ in range(3)]
        c = self.card()
        srv = S.WikiServer(('127.0.0.1', 8788), S.Handler, bind_and_activate=False)
        self.addCleanup(srv.server_close)
        srv.server_port = 8788
        handler = S.Handler.__new__(S.Handler)
        handler.server = srv
        handler.path = '/'
        handler.headers = {'Host': 'localhost:8788'}
        handler._page = lambda *args: None
        errors = []
        handler._error = lambda ex: errors.append(ex)
        def sync():
            ready.set()
            release.wait(3)
            H.ensure_base(self.root, c['id'], c['_path'])
            from types import SimpleNamespace
            return SimpleNamespace()
        with patch.object(S.R, 'Snap', sync), patch.object(S.V, 'main_page', return_value=('test','','','')):
            thread = threading.Thread(target=handler.do_GET, daemon=True)
            thread.start()
            self.assertTrue(ready.wait(1))
            drain = threading.Thread(target=lambda: (srv.drain(), drained.set()), daemon=True)
            drain.start()
            try:
                self.assertFalse(drained.wait(.1), 'GET history writer was abandoned')
            finally:
                release.set()
                thread.join(2)
                drain.join(2)
        self.assertTrue(drained.is_set())
        self.assertFalse(errors)
        self.assertEqual(H.entries(self.root,c['id'])[0]['text'], c['_raw'])

    def test_12_no_new_history_writers_after_shutdown(self):
        import io
        self.card()
        srv = S.WikiServer(('127.0.0.1', 8788), S.Handler, bind_and_activate=False)
        self.addCleanup(srv.server_close)
        srv.server_port = 8788
        srv.stop_mutations()
        for token in (S.TOKEN, 'outdated-token'):
            handler = S.Handler.__new__(S.Handler)
            handler.server = srv
            body = ('token='+token).encode()
            handler.headers = {'Host': 'localhost:8788', 'Content-Length': str(len(body))}
            handler.rfile = io.BytesIO(body)
            statuses = []
            handler._plain = lambda status, text: statuses.append(status)
            handler._page = lambda *args: None
            handler._post = lambda form: self.fail('a stopped server admitted a new mutation')
            handler.do_POST()
            self.assertEqual(statuses, [503])
        self.assertEqual(H.entries(self.root, 'a-000001'), [])

    def test_17_cli_stop_reports_drain_timeout(self):
        from atlas_cli import cli as C
        with patch.object(S, 'stop', side_effect=RuntimeError('still draining active writes')), \
             patch.object(C, 'say_error') as error:
            with self.assertRaises(SystemExit) as ex: C.main(['wiki', '--stop'])
        self.assertEqual(ex.exception.code, 1)
        self.assertIn('still draining', error.call_args.args[0])
