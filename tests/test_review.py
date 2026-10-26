from .support import *

class ReviewTests(InventoryTest):
    def test_01_repeat_retire(self):
        c = self.card()
        dest = A.retire(c)
        before = dest.read_text()
        self.assertEqual(A.retire(A.parse(dest)), dest)
        self.assertEqual(dest.read_text(), before)
        self.assertEqual(len(H.entries(self.root, c['id'])), 2)

    def test_02_literal_scan_paths(self):
        from atlas_cli import scan
        import shlex
        class Users:
            def of(self, path): return []
        names = ['has spaces', 'quote\' and "', '$(touch INJECTED)', '`touch INJECTED`', 'semi;touch INJECTED', '$HOME', 'line\nbreak']
        for name in names:
            with self.subTest(name=name), patch.object(scan, 'other_clones', return_value=[]):
                folder = self.root / name
                folder.mkdir()
                facts = scan.inspect(folder, Users())
                self.assertEqual(shlex.split(facts['entry']), ['cd', str(folder.resolve())])
                r = subprocess.run(facts['check'], shell=True, cwd=self.root)
                self.assertEqual(r.returncode, 0)
                self.assertFalse((self.root / 'INJECTED').exists())

    def test_03_lifecycle_collisions(self):
        for action, folder, personal in [('retire', 'retired', False), ('promote', 'cards', False),
                                          ('unretire', 'inbox', False), ('share', 'cards', True)]:
            with self.subTest(action=action):
                source_folder = 'inbox' if action == 'promote' else 'retired' if action == 'unretire' else 'cards'
                c = self.card(action, folder=source_folder, personal=personal)
                other = self.card(action, cid='a-000002', folder=folder, title='Other')
                before, target = c['_path'].read_text(), other['_path'].read_text()
                with self.assertRaises(ValueError):
                    if action == 'share': A.set_personal(c, False)
                    elif action == 'promote': A.promote(c, force=True)
                    else: getattr(A, action)(c)
                self.assertEqual(c['_path'].read_text(), before)
                self.assertEqual(other['_path'].read_text(), target)

    def test_04_stale_process_and_atomic_save(self):
        c = self.card()
        old = c['_path'].read_text()
        code = '''from atlas_cli import core as A
c=A.load()[0]
c['what']='new wiki edit'
A.save(c,'new','wiki')'''
        self.finish(self.process(code))
        c['what'] = 'stale CLI'
        with self.assertRaisesRegex(ValueError, 'changed|conflict'):
            A.save(c, 'old')
        self.assertEqual(A.parse(c['_path'])['what'], 'new wiki edit')
        self.assertIn(old, [h['text'] for h in H.entries(self.root, c['id'])])
        fresh = A.parse(c['_path'])
        fresh['what'] = 'atomic'
        original = pathlib.Path.write_text
        def no_direct(path, *args, **kwargs):
            self.assertNotEqual(path, c['_path'], 'card writes must use atomic replacement')
            return original(path, *args, **kwargs)
        with patch.object(pathlib.Path, 'write_text', no_direct):
            A.save(fresh, 'atomic')

    def test_05_external_preimage(self):
        for action in ('confirm', 'promote', 'retire', 'unretire', 'personal'):
            with self.subTest(action=action):
                folder = 'inbox' if action == 'promote' else 'retired' if action == 'unretire' else 'cards'
                c = self.card(action, folder=folder)
                H.ensure_base(self.root, c['id'], c['_path'])
                external = c['_path'].read_text().replace('what: fake', 'what: external version')
                c['_path'].write_text(external)
                c = A.parse(c['_path'])
                if action == 'personal': A.set_personal(c)
                elif action == 'promote': A.promote(c, force=True)
                else: getattr(A, action)(c)
                self.assertIn(external, [h['text'] for h in H.entries(self.root, c['id'])])

    def test_04_simultaneous_writers(self):
        import time
        self.card()
        code = '''import pathlib,sys,time
from atlas_cli import core as A
c=A.load()[0]
(A.ROOT / ('ready'+sys.argv[1])).touch()
while not (A.ROOT/'go').exists(): time.sleep(.005)
c['what']=sys.argv[1]
try: A.save(c,'race'); print('saved')
except ValueError: print('conflict')
'''
        ps = [self.process(code, n) for n in ('1', '2')]
        deadline = time.monotonic() + 5
        while not all((self.root / ('ready'+n)).exists() for n in ('1', '2')):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.01)
        (self.root / 'go').touch()
        results = [self.finish(p).strip() for p in ps]
        self.assertEqual(sorted(results), ['conflict', 'saved'])
        self.assertEqual(len(H.entries(self.root, 'a-000001')), 2)

    def test_04_promotion_rejects_edit_during_check(self):
        c = self.card(folder='inbox', check='true')
        def concurrent(cards):
            fresh = A.parse(c['_path'])
            fresh['what'] = 'edited during check'
            A.save(fresh, 'wiki edit', 'wiki')
            return {c['id']: {'ok': True}}
        with patch.object(A, 'run_checks', concurrent), self.assertRaises(ValueError):
            A.promote(c)
        self.assertEqual(A.parse(c['_path'])['what'], 'edited during check')

    def test_06_frontmatter_roundtrip(self):
        values = ['"literal quotes"', "'single'", 'Acme, Inc.', 'text  # not a comment',
                  'line one\nline two\r\tend', r'C:\path\thing', '[brackets]', ' spaced ',
                  'echo "hi  # there"', 'x: y', '', '雪']
        for value in values:
            with self.subTest(value=value):
                c = self.card(title=value, aliases=[value, 'other, name'], notes=[value], check=value)
                for key in ('title', 'check'):
                    self.assertEqual(c[key], value)
                self.assertEqual(c['aliases'], [value, 'other, name'])
                self.assertEqual(c['notes'], [value])
                A.save(c, 'roundtrip')
                self.assertEqual(A.parse(c['_path'])['title'], value)
        path = self.root / 'cards/legacy.md'
        path.write_text("---\nid: a-000002\n# old comment\ntitle: Plain  # comment\naliases: ['Acme, Inc.', Other]\nnotes: []\ncheck: echo 'hi  # there'  # comment\n---\nbody\n")
        c = A.parse(path)
        self.assertEqual(c['title'], 'Plain')
        self.assertEqual(c['aliases'], ['Acme, Inc.', 'Other'])
        self.assertEqual(c['check'], "echo 'hi  # there'")
        self.assertEqual(c['_body'], 'body\n')

    def test_07_history_ids(self):
        for cid in ('../escaped', str(self.root / 'escaped'), 'a-ffffff/../../escape', 'a-000001\n', 'bad'):
            with self.subTest(cid=cid), self.assertRaises(ValueError):
                H.record(self.root, cid, 'text', 'bad', 'wiki')
        self.assertFalse((self.root / 'escaped.jsonl').exists())
        directory = self.root / '.state/history'
        directory.mkdir(parents=True, exist_ok=True)
        outside = self.root / 'outside.jsonl'
        (directory / 'a-000001.jsonl').symlink_to(outside)
        with self.assertRaises(ValueError): H.record(self.root, 'a-000001', 'text', 'bad', 'wiki')

    def test_08_history_tails(self):
        p = self.root / '.state/history/a-000001.jsonl'
        p.parent.mkdir(parents=True)
        valid = json.dumps(dict(at='2026-01-01', by='cli', summary='base', text='first'))
        for tail in (valid, valid + '\n{"text":"interrupted', valid + '\n{"text":'):
            with self.subTest(tail=tail):
                p.write_text(tail)
                H.record(self.root, 'a-000001', 'second', 'next', 'cli')
                self.assertEqual([h['text'] for h in H.entries(self.root, 'a-000001')], ['first', 'second'])
                self.assertTrue(p.read_text().endswith('\n'))
        p.write_text(valid + '\nBROKEN\n' + valid + '\n')
        with self.assertRaisesRegex(ValueError, 'history|History'):
            H.record(self.root, 'a-000001', 'third', 'fail closed', 'cli')

    def test_08_history_concurrent_append(self):
        code = '''from atlas_cli import core as A, history as H
import sys
for i in range(30): H.record(A.ROOT,'a-000001',sys.argv[1]+str(i),'concurrent','cli')
'''
        ps = [self.process(code, n) for n in ('a', 'b', 'c')]
        for p in ps: self.finish(p)
        entries = H.entries(self.root, 'a-000001')
        self.assertEqual(len(entries), 90)
        self.assertEqual(len({e['text'] for e in entries}), 90)

    def test_09_revision_in_memory(self):
        from atlas_cli.wiki import render as R
        from concurrent.futures import ThreadPoolExecutor
        c = self.card()
        texts = [A.dump({**c, 'title': 'Version ' + str(n)}) for n in range(40)]
        def no_write(*args, **kwargs):
            self.fail('revision GET must not write shared temporary files')
        with patch.object(pathlib.Path, 'write_text', no_write), ThreadPoolExecutor(8) as pool:
            parsed = list(pool.map(lambda text: R.parse_text(text, c), texts))
        self.assertEqual([p['title'] for p in parsed], ['Version ' + str(n) for n in range(40)])
        self.assertFalse((self.root / '.state/rev.md').exists())

    def _wait_file(self, name):
        import time
        deadline = time.monotonic() + 5
        while not (self.root / name).exists():
            self.assertLess(time.monotonic(), deadline, name)
            time.sleep(.01)

    def test_10_check_process_merge(self):
        for n in (1, 2):
            self.card('thing'+str(n), cid=f'a-00000{n}', check=f'touch ready{n}; while ! test -e go{n}; do sleep .01; done; true')
        code = "from atlas_cli import core as A; import sys; A.run_checks([A.find(sys.argv[1])])"
        p1, p2 = self.process(code, 'thing1'), self.process(code, 'thing2')
        self._wait_file('ready1')
        self._wait_file('ready2')
        (self.root / 'go1').touch()
        self.finish(p1)
        (self.root / 'go2').touch()
        self.finish(p2)
        self.assertEqual(set(A.state()), {'a-000001', 'a-000002'})

    def test_10_blocked_check_keeps_concurrent_success(self):
        c = self.card(check='touch ready; while ! test -e go; do sleep .01; done; echo "Operation not permitted"; false')
        A.STATE.parent.mkdir(parents=True)
        A.STATE.write_text(json.dumps({c['id']: {'ok': False, 'at': 'old', 'out': 'old'}}))
        code = "from atlas_cli import core as A; from atlas_cli.wiki import actions as X; X._checks(A.load())"
        p = self.process(code)
        self._wait_file('ready')
        fresh = {**c, 'check': 'true'}
        A.save(fresh, 'persist replacement check')
        A.run_checks([fresh])
        (self.root / 'go').touch()
        self.finish(p)
        self.assertTrue(A.state()[c['id']]['ok'])

    def test_11_rendered_snapshot_token(self):
        from atlas_cli.wiki import render as R, actions as X, server as S
        c = self.card()
        snap = R.Snap()
        old = c['_path'].read_text()
        changed = {**c, 'what': 'newer version'}
        A.save(changed, 'intervening')
        handler = S.Handler.__new__(S.Handler)
        from types import SimpleNamespace
        from contextlib import nullcontext
        handler.server = SimpleNamespace(mutation=nullcontext)
        handler.path = '/wiki/thing/edit'
        captured = []
        handler._page = lambda snap, view: captured.append(view)
        with patch.object(R, 'Snap', return_value=snap): handler._get()
        self.assertIn('value="'+X.digest(old)+'"', captured[0][1])
        form = {'base': X.digest(old), 'title': c['title'], 'body': 'stale form', 'do': 'save'}
        result = X.save_edit(snap, c, form)
        self.assertEqual(result[0], 'page')
        self.assertIn('changed while', result[1][1])
        self.assertEqual(A.parse(c['_path'])['what'], 'newer version')

    def test_13_personal_parent_directories(self):
        c = self.card(personal=True)
        self.assertFalse((self.root / 'retired').exists())
        dest = A.retire(c)
        self.assertEqual(dest, self.root / 'retired/personal/thing.md')
        self.assertTrue(dest.exists())
        dest = A.unretire(A.parse(dest))
        self.assertEqual(dest, self.root / 'inbox/personal/thing.md')
        self.assertTrue(dest.exists())
        # A new personal draft also works without any preexisting inbox.
        import shutil
        shutil.rmtree(self.root / 'inbox')
        self.assertTrue(A.new_card('Brand new', 'folder', 'mac', personal=True)['_path'].exists())

    def test_14_related_comma_title(self):
        from atlas_cli.wiki import render as R, actions as X, views as V
        other = self.card('acme', cid='a-000002', title='Acme, Inc.')
        c = self.card(links=[other['id']])
        snap = R.Snap()
        form = V.form_values(snap, c)
        form.update(base=X.digest(c['_raw']), do='save')
        result = X.save_edit(snap, c, form)
        self.assertEqual(result[0], 'redirect')
        self.assertEqual(A.parse(c['_path'])['links'], [other['id']])
        self.assertEqual(X._links(snap, 'Acme, Inc.')[0], [other['id']])

    def test_15_rename_collision(self):
        from atlas_cli.wiki import render as R, actions as X, views as V
        other = self.card('other', cid='a-000002', title='Existing', aliases=['Old Name'])
        c = self.card()
        for title in ('Existing', 'eXiStInG', 'Old Name', 'other', other['id']):
            snap = R.Snap()
            form = V.form_values(snap, c)
            form.update(title=title, base=X.digest(c['_raw']), do='save')
            result = X.save_edit(snap, c, form)
            self.assertEqual(result[0], 'page', title)
            self.assertEqual(A.parse(c['_path'])['title'], 'Thing')
        snap = R.Snap()
        form = V.form_values(snap, c)
        form.update(title='Unique', base=X.digest(c['_raw']), do='save')
        self.assertEqual(X.save_edit(snap, c, form)[0], 'redirect')
        saved = A.parse(c['_path'])
        self.assertIn('Thing', saved['aliases'])

    def test_16_check_process_group_timeout(self):
        import shlex
        import time
        A.CFG['check_timeout'] = .15
        child = "import pathlib,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path('child.pid').write_text(str(__import__('os').getpid())); time.sleep(.7); pathlib.Path('escaped').touch()"
        c = self.card(check=shlex.quote(sys.executable)+' -c '+shlex.quote(child)+'; true')
        start = time.monotonic()
        result = A.run_checks([c])[c['id']]
        self.assertFalse(result['ok'])
        self.assertIn('timed out', result['out'])
        self.assertLess(time.monotonic()-start, .65)
        time.sleep(.8)
        self.assertFalse((self.root / 'escaped').exists(), 'timed out descendant continued side effects')

    def test_18_no_check_precedence(self):
        from atlas_cli import cli as C
        self.card(check='false')
        for argv in (['map', '--no-check'], ['today', '--no-check'], ['map', '--check', '--no-check']):
            with self.subTest(argv=argv), patch.object(C, 'TTY', False), patch.object(C, 'wiki_quietly'), \
                 patch.object(C, 'checks', return_value={}) as checks, patch.object(C, 'print_map'), patch.object(C.out, 'print'):
                C.cmd_map(C.parser().parse_args(argv))
                checks.assert_not_called()

    def test_19_empty_inventory_and_scan(self):
        from atlas_cli import cli as C
        from atlas_cli import scan as SC
        with patch.object(C.out, 'print'):
            C.print_map([], {})
            c = self.card()
            A.retire(c)
            C.print_map(A.load(), {})
            for loose in (False, True):
                if loose: (self.root / 'loose.txt').touch()
                args = C.parser().parse_args(['scan', str(self.root), '--dry-run'])
                with patch.object(SC, 'scan', return_value=iter([])):
                    C.cmd_scan(args)

    def test_20_editor_arguments(self):
        from atlas_cli import cli as C
        c = self.card()
        cases = [('code --wait', ['code', '--wait']), ('emacsclient -c', ['emacsclient', '-c']),
                 ('"/Applications/My Editor/bin/edit" --wait', ['/Applications/My Editor/bin/edit', '--wait'])]
        class Exec(Exception): pass
        for value, expected in cases:
            with self.subTest(editor=value), patch.dict(os.environ, EDITOR=value), \
                 patch.object(C.os, 'execvp', side_effect=Exec) as call:
                with self.assertRaises(Exec): C.cmd_open(C.parser().parse_args(['open', 'thing', '--edit']))
                call.assert_called_once_with(expected[0], expected+[str(c['_path'])])

    def test_21_interactive_flags(self):
        from atlas_cli import cli as C
        async def accept(title, fields, **kwargs):
            return {f.key: f.value for f in fields}
        flags = {'where': '/fake path', 'what': 'A thing', 'why': 'Needed', 'source': 'fake source',
                 'entry': 'fake entry', 'check': 'test -d /fake'}
        argv = ['new', 'Flagged', '--personal', '--link', 'a-000002']
        for k, v in flags.items(): argv += ['--'+k, v]
        with patch.object(C, 'TTY', True), patch.object(C.W, 'form', accept), patch.object(C.out, 'print'):
            C.cmd_new(C.parser().parse_args(argv))
        c = A.load()[0]
        for k, v in flags.items(): self.assertEqual(c[k], v, k)
        self.assertEqual(c['links'], ['a-000002'])
        self.assertTrue(c['_personal'])

    def test_22_bounded_scan_traversal(self):
        from atlas_cli import scan as SC
        class Users:
            def of(self, path): return []
        visited = []
        def paths(path, **kwargs):
            for i in range(5001):
                if i == 5000: self.fail('traversal consumed beyond the file budget')
                visited.append(i)
                yield str(self.root), [], ['one.txt']
        (self.root / 'one.txt').touch()
        with patch('os.walk', paths), patch.object(SC, 'other_clones', return_value=[]):
            facts = SC.inspect(self.root, Users())
        self.assertEqual(len(visited), 5000)
        self.assertIn('5000 files', facts['facts'][0])

    def test_22_prunes_dependency_trees(self):
        from atlas_cli import scan as SC
        class Users:
            def of(self, path): return []
        (self.root / 'node_modules').mkdir()
        (self.root / 'node_modules/vendor.js').touch()
        with patch.object(SC, 'other_clones', return_value=[]):
            facts = SC.inspect(self.root, Users())
        self.assertNotRegex(facts['facts'][0], r'\d+ \.js(?:,|\))')

    def test_23_personal_markdown_links(self):
        for folder in ('inbox', 'cards', 'retired'):
            c = self.card(folder=folder, personal=True)
            self.assertEqual(A.linkname(c), f'[[{folder}/personal/thing|Thing]]')
        A.build_md(A.load(), {})
        text = (self.root / 'ATLAS.md').read_text()
        for folder in ('inbox', 'cards', 'retired'):
            self.assertIn(f'[[{folder}/personal/thing|Thing]]', text)

    def test_24_recent_changes_follow_renames(self):
        from atlas_cli.wiki import render as R, views as V
        c = self.card('old')
        def git(*args):
            r = subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, text=True,
                               env={**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull})
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout
        git('init', '-q')
        git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'user.name', 'Fixture')
        git('add', 'cards/old.md')
        git('commit', '-qm', 'original card')
        git('mv', 'cards/old.md', 'cards/middle.md')
        git('commit', '-qm', 'first rename')
        git('mv', 'cards/middle.md', 'cards/new.md')
        git('commit', '-qm', 'second rename')
        snap = R.Snap()
        events = [ev for ev in V.events(snap) if ev[2] == 'git']
        self.assertEqual({ev[3] for ev in events}, {'original card', 'first rename', 'second rename'})
        self.assertTrue(all(ev[1]['id'] == c['id'] for ev in events))
        self.assertEqual(len(events), 3)

    def test_25_complete_slash_page_names(self):
        from atlas_cli.wiki import render as R
        full = self.card('ci-cd', title='CI/CD')
        self.card('cd', cid='a-000002', title='CD')
        snap = R.Snap()
        self.assertEqual(snap.resolve('CI/CD'), ('/wiki/ci-cd', 'CI/CD', True))
        self.assertEqual(snap.resolve('cards/ci-cd'), ('/wiki/ci-cd', 'CI/CD', True))
        self.assertEqual(snap.resolve('cards/personal/ci-cd.md'), ('/wiki/ci-cd', 'CI/CD', True))
        self.assertEqual(snap.resolve('Unknown/CD')[2], False)
        self.assertEqual(snap.resolve('Unknown/CD')[1], 'Unknown/CD')

    def test_26_suggestion_cancellation(self):
        r = subprocess.run(['node', 'tests/suggestions.cjs'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assertIn('6 suggestion cancellation scenarios passed', r.stdout)

    def test_04_cli_reports_safe_conflicts(self):
        from atlas_cli import cli as C
        self.card()
        with patch.object(A, 'confirm', side_effect=A.Conflict('changed; reload')), \
             patch.object(C, 'say_error') as error:
            with self.assertRaises(SystemExit) as ex: C.main(['confirm', 'thing'])
        self.assertEqual(ex.exception.code, 1)
        self.assertIn('changed', error.call_args.args[0])

    def test_04_load_serializes_with_lifecycle_move(self):
        import time
        c = self.card()
        code = '''from atlas_cli import core as A
(A.ROOT/'ready').touch()
A.retire(A.load()[0])
(A.ROOT/'moved').touch()
'''
        original = A.parse
        processes = []
        def parse_while_move_waits(path):
            p = self.process(code)
            processes.append(p)
            self._wait_file('ready')
            time.sleep(.1)
            self.assertFalse((self.root/'moved').exists(), 'load exposed a file to concurrent removal')
            return original(path)
        with patch.object(A, 'parse', parse_while_move_waits):
            try: cards = A.load()
            finally:
                for p in processes: self.finish(p)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['_raw'], c['_raw'])

    def test_15_restore_rejects_name_collision(self):
        c = self.card()
        self.card('other', cid='a-000002', title='Existing')
        historical = A.dump({**c, 'title': 'Existing'})
        with self.assertRaises(A.Conflict): A.save(c, 'restore', text=historical)
        self.assertEqual(A.parse(c['_path'])['title'], 'Thing')

    def test_06_raw_crlf_preimage(self):
        c = self.card()
        raw = c['_raw'].replace('\n', '\r\n')
        c['_path'].write_bytes(raw.encode())
        c = A.parse(c['_path'])
        self.assertEqual(c['_raw'], raw)
        A.confirm(c)
        self.assertEqual(H.entries(self.root, c['id'])[0]['text'], raw)

    def test_03_edit_share_collision_is_unchanged(self):
        from atlas_cli.wiki import render as R, actions as X, views as V
        c = self.card(personal=True)
        self.card(cid='a-000002', title='Other owner')
        snap = R.Snap()
        form = V.form_values(snap, c)
        form.update(personal='', what='unsaved change', base=X.digest(c['_raw']), do='save')
        try:
            result = X.save_edit(snap, c, form)
            self.assertEqual(result[0], 'page')
        except A.Conflict:
            pass
        self.assertEqual(c['_path'].read_text(), c['_raw'])
        self.assertEqual(A.parse(c['_path'])['what'], 'fake')

    def test_06_plain_apostrophe_comments(self):
        path = self.root / 'cards/legacy.md'
        path.write_text("---\nid: a-000001\ntitle: Clark's machine  # comment\nnotes: []\n---\nBody\n")
        self.assertEqual(A.parse(path)['title'], "Clark's machine")

    def test_08_history_invalid_entry_rejected(self):
        with self.assertRaisesRegex(ValueError, 'history|History'):
            H.record(self.root, 'a-000001', 'text', None, 'cli')
        path = self.root / '.state/history/a-000001.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"text":"valid JSON but wrong shape"}')
        with self.assertRaisesRegex(ValueError, 'history|History'):
            H.record(self.root, 'a-000001', 'second', 'valid', 'cli')

    def test_04_wiki_and_cli_race(self):
        self.card()
        cli = '''from atlas_cli import core as A
import time
c=A.load()[0]
(A.ROOT/'cli-ready').touch()
while not (A.ROOT/'go').exists(): time.sleep(.005)
try: A.confirm(c); print('saved')
except A.Conflict: print('conflict')
'''
        wiki = '''from atlas_cli import core as A
from atlas_cli.wiki import render as R, actions as X, views as V
import time
snap=R.Snap(); c=snap.cards[0]; form=V.form_values(snap,c)
form.update(base=X.digest(c['_raw']), what='wiki race edit', do='save')
(A.ROOT/'wiki-ready').touch()
while not (A.ROOT/'go').exists(): time.sleep(.005)
r=X.save_edit(snap,c,form)
print('saved' if r[0]=='redirect' else 'conflict')
'''
        ps = [self.process(cli), self.process(wiki)]
        self._wait_file('cli-ready')
        self._wait_file('wiki-ready')
        (self.root / 'go').touch()
        self.assertEqual(sorted(self.finish(p).strip() for p in ps), ['conflict', 'saved'])
        self.assertEqual(len(H.entries(self.root,'a-000001')), 2)

    def test_04_atomic_replace_failure_preserves_file(self):
        from atlas_cli.storage import atomic_write
        c = self.card()
        with patch('atlas_cli.storage.os.replace', side_effect=OSError('simulated failure')):
            with self.assertRaises(OSError): atomic_write(c['_path'], 'replacement')
        self.assertEqual(c['_path'].read_text(), c['_raw'])
        self.assertEqual(list(c['_path'].parent.glob('.thing.md-*')), [])

    def test_08_partial_utf8_tail_is_quarantined(self):
        p = self.root / '.state/history/a-000001.jsonl'
        H.record(self.root, 'a-000001', 'first', 'base', 'cli')
        tail = b'{"text":"\xe9\x9b'
        with p.open('ab') as f: f.write(tail)
        H.record(self.root, 'a-000001', 'second', 'recovered', 'cli')
        self.assertEqual([e['text'] for e in H.entries(self.root,'a-000001')], ['first','second'])
        fragments = list(p.parent.glob(p.name+'.tail-*'))
        self.assertEqual(len(fragments), 1)
        self.assertEqual(fragments[0].read_bytes(), tail)
