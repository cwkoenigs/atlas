"""Lifecycle concurrency uses disposable process fixtures, without TCP binding."""
from .support import *
import threading
import time
from atlas_cli.wiki import server as S


class LifecycleTests(InventoryTest):
    def test_simultaneous_threads_start_only_one_server(self):
        gate=threading.Barrier(2); running=[]; launches=[]; results=[]; errors=[]
        def health(): return running[0] if running else None
        def start(wait=True):
            launches.append(1); time.sleep(.1)
            running[:]=[dict(app='atlas-wiki',version=S.VERSION,root=str(self.root),port=S.port(),pid=123,instance='fixture')]
            return 123
        def call():
            try: gate.wait(2); results.append(S.ensure())
            except BaseException as ex: errors.append(ex)
        with patch.object(S,'health',health), patch.object(S,'start',start):
            threads=[threading.Thread(target=call) for _ in range(2)]
            for t in threads: t.start()
            for t in threads: t.join(3)
        self.assertEqual(errors,[]); self.assertEqual(len(launches),1)
        self.assertEqual(sorted(results),['running','started'])

    def test_independent_processes_serialize_start_and_restart(self):
        for restart in (False,True):
            marker=self.root/'fixture-listener.json'; calls=self.root/'fixture-calls'
            if marker.exists(): marker.unlink()
            if calls.exists(): calls.unlink()
            if restart: marker.write_text(json.dumps(dict(app='atlas-wiki',version='old',root=str(self.root),port=S.port(),pid=123,instance='old')))
            code='''from atlas_cli.wiki import server as S
from atlas_cli import core as A
import json,time
marker=A.ROOT/'fixture-listener.json'; calls=A.ROOT/'fixture-calls'
def health(): return json.loads(marker.read_text()) if marker.exists() else None
def start(wait=True):
    with calls.open('a') as f: f.write('start\\n')
    time.sleep(.15)
    marker.write_text(json.dumps(dict(app='atlas-wiki',version=S.VERSION,root=str(A.ROOT),port=S.port(),pid=123,instance='new')))
    return 123
def stop():
    with calls.open('a') as f: f.write('stop\\n')
    time.sleep(.1); marker.unlink(); return True
S.health=health; S.start=start; S.stop=stop
print(S.ensure())
'''
            workers=[self.process(code) for _ in range(2)]
            results=[self.finish(p).strip() for p in workers]
            self.assertEqual(calls.read_text().splitlines(),['stop','start'] if restart else ['start'])
            self.assertIn('running',results)

    def test_restart_does_not_hold_inventory_lock_while_draining(self):
        from atlas_cli.storage import locked
        meta=dict(app='atlas-wiki',version='old',root=str(self.root),port=S.port(),pid=123,instance='fixture')
        finished=threading.Event(); threads=[]
        def writer():
            with locked(self.root): finished.set()
        def stop():
            t=threading.Thread(target=writer); threads.append(t); t.start()
            self.assertTrue(finished.wait(1),'lifecycle held inventory lock while draining')
        with patch.object(S,'health',return_value=meta), patch.object(S,'stop',stop), patch.object(S,'start'):
            S.ensure()
        for t in threads: t.join(2)

    def test_identity_validation_and_foreign_occupant(self):
        meta=dict(app='atlas-wiki',version=S.VERSION,root=str(self.root),port=S.port(),pid=123,instance='fixture')
        for changed in (dict(app='other'),dict(root='/other/inventory')):
            with patch.object(S,'health',return_value={**meta,**changed}), patch.object(S,'start') as start, patch.object(S,'stop') as stop:
                with self.assertRaises(RuntimeError): S.ensure()
                start.assert_not_called(); stop.assert_not_called()
        for changed in (dict(version='old'),dict(port=S.port()+1)):
            with patch.object(S,'health',return_value={**meta,**changed}), patch.object(S,'start') as start, patch.object(S,'stop') as stop:
                self.assertIn('restarted',S.ensure()); start.assert_called_once(); stop.assert_called_once()

    def test_probe_does_not_relabel_wrong_reported_port(self):
        import io
        meta=dict(app='atlas-wiki',version=S.VERSION,root=str(self.root),port=S.port()+1,pid=123,instance='fixture')
        with patch.object(S.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(meta).encode())):
            self.assertEqual(S._probe(S.port(),.1),dict(app='other'))

    def test_health_does_not_adopt_wrong_instance_from_old_port(self):
        path=self.root/'.state/wiki-server.json'; path.parent.mkdir()
        meta=dict(app='atlas-wiki',version=S.VERSION,root=str(self.root),port=S.port()+1,pid=123,instance='previous')
        path.write_text(json.dumps(meta))
        def probe(port,timeout): return {**meta,'instance':'replacement'} if port==meta['port'] else None
        with patch.object(S,'_probe',probe): self.assertIsNone(S.health())

    def test_direct_start_and_wait_false_adopt_verified_listener(self):
        from types import SimpleNamespace
        current=[]; launched=[]; gate=threading.Barrier(2); errors=[]; results=[]
        meta=dict(app='atlas-wiki',version=S.VERSION,root=str(self.root),port=S.port(),pid=123,instance='fixture')
        def spawn(*args,**kwargs):
            launched.append(1)
            return SimpleNamespace(pid=123,poll=lambda: None)
        def run():
            try: gate.wait(2); results.append(S.start(wait=False))
            except BaseException as ex: errors.append(ex)
        real_sleep=time.sleep
        def ready(seconds):
            real_sleep(.01); current[:]=[meta]
        with patch.object(S,'health',side_effect=lambda: current[0] if current else None), \
             patch.object(S.subprocess,'Popen',spawn), patch.object(S.time,'sleep',ready):
            threads=[threading.Thread(target=run) for _ in range(2)]
            for t in threads: t.start()
            for t in threads: t.join(3)
        self.assertEqual(errors,[]); self.assertEqual(launched,[1]); self.assertEqual(results,[123,123])
