"""Git blob rendering and restore preserve exact CRLF and final-newline bytes."""
from .support import *
from atlas_cli.wiki import render as R, actions as X, views as V


class GitRevisionTests(InventoryTest):
    def git(self,*args):
        result=subprocess.run(['git','-C',str(self.root),*args],capture_output=True,
                              env={**os.environ,'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull})
        self.assertEqual(result.returncode,0,result.stderr.decode()); return result.stdout

    def test_git_crlf_revision_render_and_restore_exact_bytes(self):
        self.git('init','-q'); self.git('config','user.name','Fixture'); self.git('config','user.email','fixture@example.invalid')
        self.git('config','core.autocrlf','false')
        for n,final in enumerate((True,False),1):
            c=self.card('crlf'+str(n),cid='a-00004'+str(n))
            raw=c['_raw'].replace('\n','\r\n')
            if not final: raw=raw.rstrip('\r\n')
            c['_path'].write_bytes(raw.encode()); self.git('add',str(c['_path'])); self.git('commit','-qm','CRLF card')
            snap=R.Snap(); c=snap.by_slug[c['_slug']]
            rev=next(r for r in R.revisions(c) if r['by']=='git')
            self.assertEqual(R.revision_text(rev).encode(),raw.encode())
            rendered=R.parse_text(R.revision_text(rev),c)
            self.assertEqual(rendered['_body'],A.parse_text(raw,c['_path'])['_body'])
            self.assertIsNotNone(V.revision(snap,c,rev['key']))
            changed={**c,'_body':'changed\n'}; A.save(changed,'change before restore')
            snap=R.Snap(); c=snap.by_slug[c['_slug']]
            self.assertEqual(X.restore(snap,c,{'key':rev['key']})[0],'redirect')
            self.assertEqual(c['_path'].read_bytes(),raw.encode())
            self.assertEqual(H.entries(self.root,c['id'])[-1]['text'].encode(),raw.encode())
