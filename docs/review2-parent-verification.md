# Independent acceptance for second-review fixes

The parent ran these checks separately from the implementing Codex session, against disposable inventories and the candidate source selected explicitly with `PYTHONPATH`. No real inventory checks or live card mutations were used.

## Results

- Repository suite: **119 tests passed** in the parent context.
- Independent positive acceptance: **9 tests passed** for external-save preservation, combined private edit failure, changed-command and same-command overlapping check generations, legacy-cache display, Unicode descriptions, historical alias ownership, exact Git CRLF restore, and three simultaneous real CLI startups.
- The corresponding baseline probes failed against `84a3e6f` before the fixes (including actual concurrent CLI startup failures and ordinary-save/private-form data loss).
- Actual Chrome: light theme default and explicit persistence; keyboard search; late responses stay dismissed; real form preview and save; 390px viewport without horizontal overflow or JavaScript errors.
- Separate HTTP acceptance: **28 checks passed**, including edit conflict, section edits, lifecycle actions, history/diff, CSRF/Origin/Host rejection and `--no-check`.
- Actual TCP/process acceptance: configured-port migration, unreaped stopped-process handling, active mutation/history drain with idle connection, forced lifecycle crash recovery, source-removal failure rollback, Ctrl-C descendant termination, CRLF local-history restore, and locked readers all passed.
- Existing-data compatibility: all **38 live card byte hashes and parsed metadata** matched the baseline in a read-only comparison under the new parser.

The cancellation probe persists its harmless fixture check before running it: the new result-binding logic deliberately rejects unsaved command changes. All spawned-check subprocesses in the independent probes inherit the candidate `PYTHONPATH`, rather than importing an older editable installation.

## Boundaries

The check cache now binds results to the current command and run generation; legacy unbound results must not be interpreted as current passes or failures. A user-authored check is still executable trusted code, not a sandboxed expression. Recovery retains local ignored claims and may require reconciliation on conflicting external changes. Linux-specific system calls and physical power-loss durability were not exercised on this macOS host.
