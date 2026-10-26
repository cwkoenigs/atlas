"""Only current commands and monotonically newer runs may supply check results."""
from .support import *
import time
from atlas_cli.wiki import actions as X


class CheckTests(InventoryTest):
    def wait_file(self,name):
        deadline=time.monotonic()+3
        while not (self.root/name).exists():
            self.assertLess(time.monotonic(),deadline,name); time.sleep(.01)

    def test_old_command_cannot_overwrite_new_result(self):
        c=self.card(check='touch started; while ! test -e release; do sleep .01; done; true')
        old=self.process('from atlas_cli import core as A; A.CFG["check_timeout"]=5; A.run_checks(A.load())')
        self.wait_file('started')
        try:
            changed=A.parse(c['_path']); changed['check']='false'; A.save(changed,'change command')
            self.assertFalse(A.run_checks([changed])[c['id']]['ok'])
        finally:
            (self.root/'release').touch(); self.finish(old)
        self.assertFalse(A.state()[c['id']]['ok'])
        self.assertEqual(A.status(changed,A.state()),('Failing','fail'))

    def test_same_command_older_run_cannot_replace_newer_commit(self):
        c=self.card(check='if test -e newer; then false; else touch started; while ! test -e release; do sleep .01; done; true; fi')
        old=self.process('from atlas_cli import core as A; A.CFG["check_timeout"]=5; A.run_checks(A.load())')
        self.wait_file('started')
        try:
            (self.root/'newer').touch(); newer=A.run_checks([c])[c['id']]
            self.assertFalse(newer['ok'])
        finally:
            (self.root/'release').touch(); self.finish(old)
        self.assertEqual(A.state()[c['id']],newer)

    def test_changed_deleted_and_stale_explicit_snapshot(self):
        for n,change in enumerate(('command','body','deleted'),1):
            c=self.card(change,cid='a-00003'+str(n),check=f'touch started{n}; while ! test -e release{n}; do sleep .01; done; true')
            old=self.process('from atlas_cli import core as A; import sys; A.CFG["check_timeout"]=5; A.run_checks([A.find(sys.argv[1])])',c['id'])
            self.wait_file('started'+str(n))
            try:
                if change=='deleted': c['_path'].unlink()
                else:
                    fresh=A.parse(c['_path']); fresh['check' if change=='command' else '_body']='false'; A.save(fresh,'edit')
            finally:
                (self.root/('release'+str(n))).touch(); self.finish(old)
            self.assertNotIn(c['id'],A.state())
            # Explicit callers holding stale dictionaries must not execute their checks.
            with patch.object(A.subprocess,'Popen',side_effect=AssertionError('stale command executed')):
                A.run_checks([c])

    def test_legacy_cache_and_edited_command_never_display_ok(self):
        c=self.card(check='true'); old={c['id']:dict(ok=True,at='2026-10-26T10:00',out='')}
        self.assertEqual(A.status(c,old),('Not checked','none'))
        current=A.run_checks([c]); self.assertEqual(A.status(c,current),('OK','ok'))
        changed=dict(c,check='false'); A.save(changed,'new command')
        self.assertEqual(A.status(changed,current),('Not checked','none'))

    def test_blocked_permissions_preserve_matching_result(self):
        c=self.card(check='test ! -e blocked || { echo "Operation not permitted"; false; }')
        previous=A.run_checks([c])[c['id']]; (self.root/'blocked').touch()
        st,blocked=X._checks([c])
        self.assertEqual(st[c['id']],previous); self.assertEqual(blocked,[c])

    def test_explicit_check_does_not_return_prior_success_after_command_edit(self):
        c=self.card(check='test ! -e slow || { touch started; while ! test -e release; do sleep .01; done; }')
        A.run_checks([c]); (self.root/'slow').touch()
        old=self.process('from atlas_cli import core as A; A.CFG["check_timeout"]=5; st=A.run_checks(A.load()); assert "a-000001" not in st, st')
        self.wait_file('started')
        try:
            changed={**c,'check':'false'}; A.save(changed,'change during explicit check')
        finally:
            (self.root/'release').touch()
        self.finish(old)
