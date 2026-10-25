"""Keep the 26-finding claim tied to discoverable, runnable regressions."""
import json
import pathlib
import unittest

class ResolutionMapTests(unittest.TestCase):
    def test_all_26_findings_have_runnable_regressions(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        rows = json.loads((root / 'docs/review-resolution.json').read_text())
        self.assertEqual([row['number'] for row in rows], list(range(1, 27)))
        self.assertEqual([sum(row['priority'] == p for row in rows) for p in ('P1','P2','P3')], [5,20,1])
        loader = unittest.TestLoader()
        for row in rows:
            self.assertTrue(row['title'])
            self.assertTrue(row['fix'])
            self.assertTrue(row['tests'])
            for name in row['tests']:
                suite = loader.loadTestsFromName(name)
                self.assertFalse(loader.errors, '\n'.join(loader.errors))
                self.assertEqual(suite.countTestCases(), 1, name)
