"""Metadata has physical LF/CRLF lines; Unicode separators remain scalar data."""
from .support import *
from atlas_cli import scan as SC


class UnicodeTests(InventoryTest):
    def test_separator_scalar_list_and_body_roundtrip(self):
        for separator in ('\u2028','\u2029','\u0085','\v','\f','\x1c','\x1d','\x1e'):
            with self.subTest(separator=repr(separator)):
                value='First'+separator+'Second'
                c=self.card(what=value,links=[value],notes=[value],_body=value+'\r\nno final newline')
                self.assertEqual(c['what'],value); self.assertEqual(c['links'],[value]); self.assertEqual(c['notes'],[value])
                self.assertEqual(c['_body'],value+'\r\nno final newline')
                head=c['_raw'].split('---\n')[1]
                self.assertNotIn(separator,head)
                self.assertEqual(A.load()[0]['what'],value)

    def test_inspect_draft_load_unicode_package_description(self):
        class Users:
            def of(self,path): return []
        project=self.root/'projects/unicode-project'; project.mkdir(parents=True)
        value='First sentence\u2028Second\u2029Third\u0085Last'
        (project/'package.json').write_text(json.dumps(dict(description=value)))
        with patch.object(SC,'other_clones',return_value=[]): finding=SC.inspect(project,Users())
        SC.draft(finding)
        card=A.load()[0]
        self.assertEqual(card['what'],value)

    def test_legacy_unicode_plain_comment_and_crlf(self):
        raw='---\r\nid: a-000001\r\ntitle: Legacy\r\nwhat: First\u2028Second  # comment\r\nnotes: ["a\u2029b", plain]\r\n---\r\nBODY\u0085\v\r\nlast'
        path=self.root/'cards/legacy.md'; path.write_bytes(raw.encode())
        c=A.parse(path)
        self.assertEqual(c['what'],'First\u2028Second'); self.assertEqual(c['notes'],['a\u2029b','plain'])
        self.assertEqual(c['_raw'],raw); self.assertEqual(c['_body'],'BODY\u0085\v\r\nlast')
        A.save(c,'exact restore',text=raw); self.assertEqual(path.read_bytes(),raw.encode())

    def test_invalid_serializer_never_publishes_new_card(self):
        with patch.object(A,'dump',return_value='invalid serialized card'):
            with self.assertRaises(ValueError): A.new_card('Invalid','folder','mac')
        self.assertEqual(A.load(),[])
