"""A repository checkout is an empty application, never somebody else's inventory."""
from .support import *
import shutil

REPO = pathlib.Path(__file__).resolve().parents[1]


class EmptyInstallTests(InventoryTest):
    def export_checkout(self):
        dest = self.root / 'checkout'
        dest.mkdir()
        names = subprocess.check_output(['git', '-C', str(REPO), 'ls-files', '-z']).decode().split('\0')
        for name in filter(None, names):
            source = REPO / name
            if source.is_file():
                out = dest / name
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, out)
        return dest

    def test_fresh_checkout_has_no_imported_cards(self):
        checkout = self.export_checkout()
        child = subprocess.run([sys.executable, '-c',
            'from atlas_cli import core as A; print(len(A.load()))'],
            env={**os.environ, 'ATLAS_DIR': str(checkout), 'PYTHONPATH': str(checkout / 'src')},
            capture_output=True, text=True, timeout=10)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(child.stdout.strip(), '0', 'A fresh install must contain zero user cards')

    def test_new_inventory_and_machine_config_are_ignored(self):
        paths = ['cards/new.md', 'inbox/new.md', 'retired/new.md',
                 'cards/personal/new.md', 'atlas.local.json', '.state/checks.json']
        child = subprocess.run(['git', '-C', str(REPO), 'check-ignore', '--no-index', '--stdin'],
                               input='\n'.join(paths)+'\n', capture_output=True, text=True)
        self.assertEqual(set(child.stdout.splitlines()), set(paths))

    def test_shipped_config_has_no_home_dashboard_or_private_hosts(self):
        cfg = json.loads((REPO / 'atlas.json').read_text())
        self.assertFalse(cfg.get('html_out'))
        self.assertFalse(cfg.get('template'))
        self.assertEqual(cfg['hosts'], {'this-mac': 'This computer'})

    def test_local_only_config_overrides_defaults_without_changing_them(self):
        base = (self.root / 'atlas.json').read_bytes()
        override = {'hosts': {'work': 'Work computer'}, 'html_out': str(self.root / 'optional.html'),
                    'template': str(self.root / 'optional-template.html')}
        (self.root / 'atlas.local.json').write_text(json.dumps(override))
        child = self.process('import json; print(json.dumps(_A.CFG))')
        cfg = json.loads(self.finish(child))
        self.assertEqual(cfg.get('hosts'), override['hosts'])
        self.assertEqual(cfg.get('html_out'), override['html_out'])
        self.assertEqual(cfg.get('template'), override['template'])
        self.assertEqual((self.root / 'atlas.json').read_bytes(), base)

    def test_wiki_snapshot_preserves_machine_local_settings(self):
        override = {'hosts': {'work': 'Work computer'}, 'stale_days': 7,
                    'check_timeout': 2, 'wiki_port': 49199}
        (self.root / 'atlas.local.json').write_text(json.dumps(override))
        child = self.process('import json; from atlas_cli.wiki import render as R, server as S; '
                             'snap=R.Snap(); print(json.dumps({"cfg":_A.CFG,"hosts":snap.hosts,"port":S.port()}))')
        result = json.loads(self.finish(child))
        for key, value in override.items():
            self.assertEqual(result['cfg'].get(key), value, key)
        self.assertEqual(result['hosts'], override['hosts'])
        self.assertEqual(result['port'], override['wiki_port'])
