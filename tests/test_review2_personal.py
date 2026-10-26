"""Content and visibility are a single transaction; private text never becomes shared."""
from .support import *
from atlas_cli.wiki import render as R, views as V, actions as X


class PersonalTests(InventoryTest):
    def form(self,c):
        snap=R.Snap(); form=V.form_values(snap,c)
        form.update(personal='yes',body='PRIVATE FAMILY DETAILS',do='save',base=X.digest(c['_raw']))
        return snap,form

    def test_private_body_never_published_in_shared_card(self):
        c=self.card(); snap,form=self.form(c); link=A.os.link
        def observe(src,dst,*args,**kwargs):
            result=link(src,dst,*args,**kwargs)
            if c['_path'].exists(): self.assertNotIn('PRIVATE FAMILY DETAILS',A.read_text(c['_path']))
            return result
        with patch.object(A.os,'link',observe), patch.object(A,'rebuild'):
            self.assertEqual(X.save_edit(snap,c,form)[0],'redirect')
        self.assertFalse(c['_path'].exists())
        self.assertIn('PRIVATE FAMILY DETAILS',A.load()[0]['_raw'])
        self.assertTrue(A.load()[0]['_personal'])

    def test_rename_failure_keeps_shared_preimage(self):
        c=self.card(); snap,form=self.form(c)
        with patch.object(A,'_rename_claim',side_effect=PermissionError('injected rename error')), patch.object(A,'rebuild'):
            with self.assertRaises(PermissionError): X.save_edit(snap,c,form)
        self.assertEqual(c['_path'].read_bytes(),c['_raw'].encode())
        self.assertEqual(A.load()[0]['_raw'],c['_raw'])

    def test_personal_crash_matrix_and_git_ignore(self):
        subprocess.run(['git','init','-q',str(self.root)],check=True,capture_output=True)
        (self.root/'.gitignore').write_text((pathlib.Path(__file__).resolve().parents[1]/'.gitignore').read_text())
        for n,point in enumerate(('stage','journal','claim','publication','history','clear'),1):
            c=self.card('private'+str(n),cid='a-00002'+str(n))
            child=self.process('''import os,sys
from atlas_cli import core as A
from atlas_cli.wiki import render as R, actions as X, views as V
point=sys.argv[1]; c=A.find(sys.argv[2]); snap=R.Snap(); form=V.form_values(snap,c)
form.update(personal='yes',body='PRIVATE FAMILY DETAILS',do='save',base=X.digest(c['_raw']))
atomic=A.atomic_write; claim=A._claim_file; link=A.os.link; record=A.H.record; clear=A._clear_save
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
    if point=='history' and args[3]=='edited': os._exit(73)
    return result
def finish():
    clear()
    if point=='clear': os._exit(73)
A.atomic_write=write; A._claim_file=capture; A.os.link=publish; A.H.record=history; A._clear_save=finish
X.save_edit(snap,c,form)
''',point,c['id'])
            out,err=child.communicate(timeout=5); self.assertEqual(child.returncode,73,out+err)
            if c['_path'].exists(): self.assertEqual(c['_path'].read_bytes(),c['_raw'].encode())
            for path in self.root.rglob('*'):
                if path.is_file() and '.git' not in path.parts and b'PRIVATE FAMILY DETAILS' in path.read_bytes():
                    result=subprocess.run(['git','-C',str(self.root),'check-ignore',str(path)],capture_output=True)
                    self.assertEqual(result.returncode,0,str(path))
            live=A.find(c['id']); self.assertEqual(live['_personal'],point!='stage')
            self.assertEqual(sum(p['id']==c['id'] for p in A.load()),1)

    def test_personal_collision_refuses_without_writes(self):
        c=self.card(); other=self.card(personal=True,cid='a-000002')
        snap,form=self.form(c); before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(A,'rebuild'): self.assertEqual(X.save_edit(snap,c,form)[0],'page')
        self.assertEqual({p:p.read_bytes() for p in before},before)
