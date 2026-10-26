"""Save/restore validates every candidate lookup name before touching history or disk."""
from .support import *
from atlas_cli.wiki import render as R, actions as X, views as V


class AliasTests(InventoryTest):
    def test_restore_refuses_alias_now_owned_by_other_card(self):
        c=self.card('original',title='Original')
        for title in ('Taken later','Current'):
            snap=R.Snap(); c=snap.by_slug['original']; form=V.form_values(snap,c)
            form.update(title=title,base=X.digest(c['_raw']),do='save')
            self.assertEqual(X.save_edit(snap,c,form)[0],'redirect')
        snap=R.Snap(); c=snap.by_slug['original']; X.restore(snap,c,{'key':'h1'})
        A.new_card('Taken later','folder','mac')
        snap=R.Snap(); c=snap.by_slug['original']
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(A.Conflict,'Taken later|taken later'): X.restore(snap,c,{'key':'h3'})
        self.assertEqual({p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)

    def test_unchanged_title_alias_collision_with_each_namespace(self):
        c=self.card('original'); self.card('other-slug',cid='a-000002',title='Other title',aliases=['Other alias'])
        H.ensure_base(self.root,c['id'],c['_path'])
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for alias in ('OTHER TITLE','Other-Slug','A-000002','other ALIAS'):
            with self.subTest(alias=alias):
                with self.assertRaises(A.Conflict): A.save({**c,'aliases':[alias]},'changed alias')
                self.assertEqual({p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)

    def test_unique_rename_keeps_old_alias_case_insensitive(self):
        c=self.card(); snap=R.Snap(); form=V.form_values(snap,c)
        form.update(title='Unique name',base=X.digest(c['_raw']),do='save')
        self.assertEqual(X.save_edit(snap,c,form)[0],'redirect')
        snap=R.Snap()
        self.assertEqual(snap.by_key['thing']['id'],c['id'])
        self.assertEqual(snap.resolve('THING')[0],'/wiki/thing')
