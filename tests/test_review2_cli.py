"""CLI outcomes must use current bound results, never raw or discarded outcomes."""
from .support import *
from atlas_cli import cli as C
import concurrent.futures
import io
import time


class CheckReportingTests(InventoryTest):
    def capture(self):
        buf = io.StringIO()
        return buf, patch.object(C, 'out', C.S.console(color=False, file=buf, width=120))

    def test_card_view_hides_legacy_passing_result(self):
        c = self.card(check='true')
        old = {c['id']: dict(ok=True, at='2026-10-24T10:00', out='')}
        buf, capture = self.capture()
        with capture:
            C.print_card(c, [c], old)
        self.assertNotIn('passed', buf.getvalue())

    def test_card_view_hides_changed_command_passing_result(self):
        c = self.card(check='true')
        old = A.run_checks([c])
        c['check'] = 'false'
        A.save(c, 'changed command')
        buf, capture = self.capture()
        with capture:
            C.print_card(c, [c], old)
        self.assertNotIn('passed', buf.getvalue())

    def test_explicit_check_reports_discarded_outcome_as_not_checked(self):
        self.card(check='touch started; while ! test -e release; do sleep .01; done; true')
        A.CFG['check_timeout'] = 5
        buf, capture = self.capture()
        with capture, concurrent.futures.ThreadPoolExecutor(1) as pool:
            future = pool.submit(C.cmd_check, C.parser().parse_args(['check']))
            deadline = time.monotonic() + 3
            try:
                while not (self.root / 'started').exists():
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.01)
                editor = self.process("from atlas_cli import core as A; c=A.load()[0]; c['check']='false'; A.save(c,'changed while checking')")
                self.finish(editor)
            finally:
                (self.root / 'release').touch()
            future.result(timeout=6)
        output = buf.getvalue()
        self.assertNotIn('all ok', output)
        self.assertNotIn('✓', output)
        self.assertIn('0 checked', output)
        self.assertIn('not checked', output)

    def test_newer_failure_is_printed_instead_of_old_callback_success(self):
        command = 'if test -e first; then rm first; touch started; while ! test -e release; do sleep .01; done; true; else false; fi'
        c = self.card(check=command)
        (self.root / 'first').touch()
        A.CFG['check_timeout'] = 5
        buf, capture = self.capture()
        with capture, concurrent.futures.ThreadPoolExecutor(1) as pool:
            future = pool.submit(C.cmd_check, C.parser().parse_args(['check']))
            deadline = time.monotonic() + 3
            try:
                while not (self.root / 'started').exists():
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.01)
                self.assertFalse(A.run_checks([c])[c['id']]['ok'])
            finally:
                (self.root / 'release').touch()
            future.result(timeout=6)
        output = buf.getvalue()
        self.assertNotIn('✓', output)
        self.assertNotIn('all ok', output)
        self.assertIn('✗', output)
        self.assertIn('1 failing', output)

    def test_genuine_current_pass_is_reported_as_success(self):
        self.card(check='true')
        buf, capture = self.capture()
        with capture:
            C.cmd_check(C.parser().parse_args(['check']))
        self.assertIn('✓', buf.getvalue())
        self.assertIn('1 checked', buf.getvalue())
        self.assertIn('all ok', buf.getvalue())

    def test_genuine_current_failure_is_reported_as_failure(self):
        self.card(check='false')
        buf, capture = self.capture()
        with capture:
            C.cmd_check(C.parser().parse_args(['check']))
        self.assertIn('✗', buf.getvalue())
        self.assertIn('1 failing', buf.getvalue())
        self.assertNotIn('all ok', buf.getvalue())

    def test_card_without_command_is_not_counted_as_checked(self):
        self.card(check='')
        buf, capture = self.capture()
        with capture:
            C.cmd_check(C.parser().parse_args(['check']))
        self.assertIn('0 checked', buf.getvalue())
        self.assertIn('1 not checked', buf.getvalue())
        self.assertNotIn('all ok', buf.getvalue())

    def test_empty_inventory_reports_nothing_to_check(self):
        buf, capture = self.capture()
        with capture:
            C.cmd_check(C.parser().parse_args(['check']))
        self.assertIn('0 checked', buf.getvalue())
        self.assertIn('nothing to check', buf.getvalue())
