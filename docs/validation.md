# Validation of the review fixes

This record covers the original 26 fixes and the six independent follow-up gates in the isolated `fix/codex-review` checkout.

The follow-up pass used tests before implementation. Initial failures and subsequent passing runs are recorded in [regression-log.md](regression-log.md). This is an uncommitted working tree for the parent to review and merge; no deploy, push, live-data repair, installed-tool change, or skill change is included. Concurrency, data preservation, and request security make this a high-risk change; the parent retains independent browser/TCP acceptance and merge/deploy ownership.

| Check | Exact command | Result |
|---|---|---|
| Full stdlib suite | `PYTHONPATH=src /Users/clarkkoenigs/.local/share/uv/tools/atlas-map/bin/python -m unittest discover -v` | 65 tests in 5.042s; OK; exit 0 |
| Follow-up regressions | `PYTHONPATH=src /Users/clarkkoenigs/.local/share/uv/tools/atlas-map/bin/python tests/run_regression.py green tests.test_followup` | 19 tests in 2.420s; OK; exit 0 |
| Compilation | `/Users/clarkkoenigs/.local/share/uv/tools/atlas-map/bin/python -m compileall -q src tests` | exit 0 |
| Theme | `PYTHONDONTWRITEBYTECODE=1 python3 /Users/clarkkoenigs/Developer/dashboard-style/scripts/check_theme.py src/atlas_cli/wiki/shell.html` | OK: 37 colors, 2 themes, 3 pages, 12 contrast pairs; exit 0 |
| Independent safety | `/Users/clarkkoenigs/.local/share/uv/tools/atlas-map/bin/python /Users/clarkkoenigs/.hermes/cache/scratch/verify-atlas-safety.py /Users/clarkkoenigs/.hermes/cache/scratch/atlas-fixes` | 12 tests in 0.039s; OK; exit 0 |
| Independent read lock | `/Users/clarkkoenigs/.local/share/uv/tools/atlas-map/bin/python /Users/clarkkoenigs/.hermes/cache/scratch/verify-atlas-read-lock.py /Users/clarkkoenigs/.hermes/cache/scratch/atlas-fixes` | PASS: readers wait for lifecycle transaction; one card seen; exit 0 |
| Patch whitespace | `git diff --check` | exit 0 |

The full suite includes the original 26-finding map validator, Node execution of six suggestion-cancellation combinations, process races, shutdown admission/drain tests over socket pairs, and the 19 new follow-up tests. Fixtures use disposable inventories and check working directories; commands come only from fixtures.

The real port probe was attempted with `/Users/clarkkoenigs/.local/share/uv/tools/atlas-map/bin/python /Users/clarkkoenigs/.hermes/cache/scratch/verify-atlas-port.py /Users/clarkkoenigs/.hermes/cache/scratch/atlas-fixes`. It was denied at the fixture's first TCP socket bind with `PermissionError: [Errno 1] Operation not permitted`. This is an environment limitation, not RED evidence or a passing TCP test.

After that sandbox run, the parent independently ran the actual Chrome, HTTP, TCP port migration, graceful TCP shutdown, forced move-crash recovery, unlink rollback, Ctrl-C descendant cleanup, CRLF restore, safety and locked-reader probes against the exact final production-code hashes. **All passed.** See [parent-verification.md](parent-verification.md) for this separate acceptance record. The browser checks used actual Chrome rather than mocked form headers.

All implementation and test checks above ran after the final implementation edit. Documentation then recorded those results. Recovery and filesystem limitations are documented in [review-resolution.md](review-resolution.md) and the README. Malformed or conflicting move intent requires reconciliation and deliberately blocks normal inventory reads rather than deleting an unknown card. No gate is intentionally left without an implementation or an automated regression.

## Final P1 external-editor race validation (2026-10-25)

This targeted pass supersedes the earlier 65-test total. Production changes are confined to the move journal, source capture, recovery, and rollback in `src/atlas_cli/core.py`. Existing follow-up move fault/crash tests now inject at the actual exclusive-rename boundary, preserving all previous semantic assertions. No commit was created; parent owns final commit/merge.

| Check | Exact command | Result |
|---|---|---|
| Full suite | `TMPDIR=$HOME/.hermes/cache/scratch PYTHONPATH=$PWD/src /Users/clarkkoenigs/.local/share/uv/tools/atlas-map/bin/python -m unittest discover -v` | 78 tests in 5.671s; OK; exit 0 |
| Compilation | `PYTHONPATH=$PWD/src /Users/clarkkoenigs/.local/share/uv/tools/atlas-map/bin/python -m compileall -q src tests` | exit 0 |
| Whitespace | `git diff --check` | exit 0 |

Exact new regression IDs (all executed by the full suite and mapped to finding 4 in `review-resolution.json`):

- `tests.test_move_claim.MoveClaimTests.test_atomic_editor_after_destination_publication`
- `tests.test_move_claim.MoveClaimTests.test_recovery_atomic_editor_after_destination_publication`
- `tests.test_move_claim.MoveClaimTests.test_source_replaced_before_claim`
- `tests.test_move_claim.MoveClaimTests.test_claim_replaced_after_rename`
- `tests.test_move_claim.MoveClaimTests.test_rollback_never_overwrites_new_original`
- `tests.test_move_claim.MoveClaimTests.test_original_created_after_claim_is_preserved`
- `tests.test_move_claim.MoveClaimTests.test_rollback_claims_replaced_destination_without_deleting_it`
- `tests.test_move_claim.MoveClaimTests.test_open_fd_edit_after_claim_validation_keeps_inode`
- `tests.test_move_claim.MoveClaimTests.test_crash_after_claim_before_history_recovers`
- `tests.test_move_claim.MoveClaimTests.test_claim_path_cannot_escape_inventory`
- `tests.test_move_claim.MoveClaimTests.test_claim_occupied_at_rename_is_never_overwritten`
- `tests.test_move_claim.MoveClaimTests.test_recovery_retains_changed_claim_for_reconciliation`
- `tests.test_move_claim.MoveClaimTests.test_reader_waits_while_source_is_claimed`

Observed RED: ten new tests failed before production changes; the additional occupied-claim test failed before replacing ordinary rename with native exclusive rename. See regression-log.md for exact results. All 13 new tests pass, together with all inherited tests. Real child-process atomic saves exercise normal and recovery after-publication interleavings. Crash recovery after claim/before history runs in a fresh process; reader locking, history idempotence, preservation of recreated originals/unknown rollback files, and late writes through open descriptors are asserted.

Limitations: native macOS exclusive rename ran successfully; Linux renameat2 was not exercised on this macOS host. Version-1/partial/corrupt journals, conflicting artifacts, and interrupted rollback deliberately require manual reconciliation. Claims/stages consume disk space and are retained without automatic deletion, including after success, to preserve late descriptor writes. Live cards, installed tools, browser/TCP deployment checks, commit/merge, push, and deployment were outside this targeted pass. Earlier parent acceptance applies to the earlier implementation; it does not attest to this final delta.
