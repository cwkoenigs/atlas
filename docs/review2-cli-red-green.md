# CLI result-reporting follow-up

Independent review found that the card view still read raw cache entries and the explicit check command printed unvalidated callback success and counted absent results as success.

Observed RED: `python -m unittest -v tests.test_review2_cli` ran the first three regressions; all three failed for the expected stale `passed` line or `all ok` success after a discarded result.

GREEN: card display now uses `A.check_result`; check output resolves fresh cards and validated outcomes after execution; missing results count as not checked. Eight focused tests pass, covering legacy and changed-command caches, discarded results, a newer same-command failure, genuine pass/fail, no command and an empty inventory. The full suite then passed 119 tests.

Commands use the installed Atlas Python, `PYTHONPATH=src`, and an explicit scratch `TMPDIR`; all inventories and check side effects are disposable fixtures.
