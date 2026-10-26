"""Save transactions preserve the actual displaced inode, including recovery boundaries."""
from .support import *
import threading
from atlas_cli.wiki import render as R, actions as X


class SaveTests(InventoryTest):
    def editor(self, path, text):
        self.finish(self.process('import os,pathlib,sys; p=pathlib.Path(sys.argv[1]); q=p.with_suffix(".editor"); q.write_bytes(sys.argv[2].encode()); os.replace(q,p)', path, text))

    def test_external_atomic_save_after_history_is_preserved(self):
        c = self.card()
        source = c['_path']
        external = A.dump({**c, '_body': 'EXTERNAL EDIT MUST SURVIVE\n'})
        base = H.ensure_base
        def interleave(*args):
            base(*args)
            self.editor(source, external)
        c['_body'] = 'Atlas edit\n'
        with patch.object(H, 'ensure_base', interleave):
            with self.assertRaises(A.Conflict): A.save(c, 'save')
        self.assertEqual(source.read_bytes(), external.encode())
        self.assertTrue(any(p.read_bytes() == external.encode() for p in self.root.rglob('*') if p.is_file()))

    def test_claim_and_publication_races_preserve_unknown_files(self):
        for boundary in ('before', 'after', 'recreated', 'publication'):
            with self.subTest(boundary=boundary):
                c = self.card(boundary, cid='a-00000'+str(('before','after','recreated','publication').index(boundary)+1))
                source = c['_path']; rename = A._rename_claim; link = A.os.link
                def capture(src, dst):
                    if src == source and boundary == 'before': self.editor(source, 'UNKNOWN\n')
                    rename(src, dst)
                    if src == source and boundary == 'after': self.editor(dst, 'UNKNOWN\n')
                    if src == source and boundary == 'recreated': self.editor(source, 'UNKNOWN\n')
                def publish(src, dst, *args, **kwargs):
                    if dst == source and boundary == 'publication': self.editor(source, 'UNKNOWN\n')
                    return link(src, dst, *args, **kwargs)
                with patch.object(A, '_rename_claim', capture), patch.object(A.os, 'link', publish):
                    with self.assertRaises((A.Conflict, FileExistsError)): A.save(c, 'save')
                self.assertEqual(source.read_bytes(), b'UNKNOWN\n')
                # Unknown artifacts require explicit reconciliation; each subcase is independent.
                journal = self.root / '.state/save.json'
                if journal.exists(): journal.rename(journal.with_suffix('.retained-'+boundary))
                source.rename(source.with_suffix('.retained'))

    def test_save_crash_matrix_and_exact_restore(self):
        for n, point in enumerate(('stage','journal','claim','publication','history','clear'), 1):
            c = self.card('crash'+str(n), cid='a-00001'+str(n))
            c['_path'].chmod(0o640)
            child = self.process('''import os,sys
from atlas_cli import core as A
point=sys.argv[1]; c=A.find(sys.argv[2]); atomic=A.atomic_write; claim=A._claim_file; link=A.os.link; record=A.H.record
clear=A._clear_save
before=c['_raw']; c['_body']='NEW BODY\\n'
def write(path,text):
    atomic(path,text)
    if (point=='stage' and path.name.startswith('.atlas-move-')) or (point=='journal' and path.name=='save.json'): os._exit(73)
def capture(src,dst):
    claim(src,dst)
    if point=='claim': os._exit(73)
def publish(src,dst,*args,**kwargs):
    link(src,dst,*args,**kwargs)
    if point=='publication' and str(dst).endswith('.md'): os._exit(73)
def history(*args,**kwargs):
    result=record(*args,**kwargs)
    if point=='history' and args[3]=='save': os._exit(73)
    return result
def finish():
    clear()
    if point=='clear': os._exit(73)
A.atomic_write=write; A._claim_file=capture; A.os.link=publish; A.H.record=history; A._clear_save=finish
A.save(c,'save')
''', point, c['id'])
            out, err = child.communicate(timeout=5)
            self.assertEqual(child.returncode, 73, out+err)
            live = A.find(c['id'])
            self.assertEqual(live['_body'], c['_body'] if point=='stage' else 'NEW BODY\n')
            self.assertEqual(live['_path'].stat().st_mode & 0o777, 0o640)
            if point!='stage':
                old = H.entries(self.root,c['id'])
                self.assertEqual(old[0]['text'], c['_raw'])
                self.assertEqual(old[-1]['text'], live['_raw'])
                A.load(); self.assertEqual(H.entries(self.root,c['id']),old)
                A.save(live,'restore',text=c['_raw'])
                self.assertEqual(live['_path'].read_bytes(), c['_raw'].encode())

    def test_rename_failure_rolls_back_and_readers_wait(self):
        c = self.card(); source=c['_path']
        with patch.object(A, '_rename_claim', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError): A.save(c, 'save')
        self.assertEqual(source.read_bytes(),c['_raw'].encode())
        self.assertEqual(A.load()[0]['_raw'],c['_raw'])
        entered, release, done = [threading.Event() for _ in range(3)]
        errors=[]; rename=A._rename_claim
        def capture(src,dst):
            rename(src,dst)
            if src==source:
                entered.set(); release.wait(3)
        def writer():
            try: A.save(c,'save')
            except BaseException as ex: errors.append(ex)
        def reader():
            try: R.Snap()
            except BaseException as ex: errors.append(ex)
            finally: done.set()
        with patch.object(A,'_rename_claim',capture):
            w=threading.Thread(target=writer); w.start()
            try:
                self.assertTrue(entered.wait(2))
                r=threading.Thread(target=reader); r.start()
                self.assertFalse(done.wait(.1))
            finally:
                release.set(); w.join(3)
                if 'r' in locals(): r.join(3)
        self.assertEqual(errors,[])
        self.assertTrue(done.is_set())

    def test_publication_failure_restores_preimage(self):
        c=self.card(); source=c['_path']; link=A.os.link
        def fail_stage(src,dst,*args,**kwargs):
            if pathlib.Path(src).name.startswith('.atlas-move-'): raise PermissionError('publication denied')
            return link(src,dst,*args,**kwargs)
        with patch.object(A.os,'link',fail_stage):
            with self.assertRaises(PermissionError): A.save({**c,'_body':'new'},'save')
        self.assertEqual(source.read_bytes(),c['_raw'].encode())
        self.assertEqual(A.load()[0]['_raw'],c['_raw'])
        self.assertFalse((self.root/'.state/save.json').exists())
        self.assertTrue(any(p.read_bytes()==c['_raw'].encode() for p in self.root.rglob('source')))

    def test_save_recovery_path_and_identity_validation_fail_closed(self):
        for n,field in enumerate(('source','dest','stage','source_claim','dest_claim','source_identity','stage_identity'),1):
            c=self.card('security'+str(n),cid='a-00005'+str(n))
            child=self.process('''import os,sys
from atlas_cli import core as A
c=A.find(sys.argv[1]); atomic=A.atomic_write
def stop(path,text):
    atomic(path,text)
    if path.name=='save.json': os._exit(73)
A.atomic_write=stop
A.save(c,'save')
''',c['id'])
            out,err=child.communicate(timeout=5); self.assertEqual(child.returncode,73,out+err)
            journal=self.root/'.state/save.json'; data=json.loads(journal.read_text())
            data[field]='../../outside'; journal.write_text(json.dumps(data))
            before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
            with self.assertRaises(A.Conflict): A.load()
            self.assertEqual({p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)
            journal.rename(journal.with_suffix('.retained-'+field))

    def test_process_reader_waits_until_save_published(self):
        c=self.card()
        writer=self.process('''from atlas_cli import core as A
import time
c=A.load()[0]; claim=A._claim_file
c['_body']='PROCESS SAVE\\n'
def hold(src,dst):
    claim(src,dst); (A.ROOT/'claimed').touch()
    while not (A.ROOT/'release').exists(): time.sleep(.01)
A._claim_file=hold
A.save(c,'save')
''')
        import time
        deadline=time.monotonic()+3
        while not (self.root/'claimed').exists():
            self.assertLess(time.monotonic(),deadline); time.sleep(.01)
        reader=self.process('from atlas_cli import core as A; assert A.load()[0]["_body"]=="PROCESS SAVE\\n"')
        try:
            time.sleep(.1); self.assertIsNone(reader.poll())
        finally:
            (self.root/'release').touch()
        self.finish(writer); self.finish(reader)

    def test_open_descriptor_edits_remain_in_claim_after_save(self):
        c=self.card(); source=c['_path']; source.chmod(0o640)
        H.ensure_base(self.root,c['id'],source); record=H.record
        with source.open('r+b') as editor:
            def edit(*args,**kwargs):
                editor.seek(0); editor.write(b'OPEN DESCRIPTOR EDIT\n'); editor.truncate()
                editor.flush(); os.fsync(editor.fileno())
                return record(*args,**kwargs)
            with patch.object(H,'record',edit): A.save({**c,'_body':'new body'},'save')
        claims=[p for p in self.root.rglob('source') if p.read_bytes()==b'OPEN DESCRIPTOR EDIT\n']
        self.assertTrue(claims); self.assertEqual(claims[0].stat().st_mode & 0o777,0o640)
        self.assertEqual(A.parse(source)['_body'],'new body')
