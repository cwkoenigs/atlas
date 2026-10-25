# Independent acceptance verification

These checks were run by the parent agent outside the Codex execution sandbox, against disposable inventories and the fixed source. They did not run the real inventory's check commands or mutate its card files.

## Results

- The repository's regression suite: **78 tests passed** with `TMPDIR` set to the Hermes scratch directory and `PYTHONPATH=src`; the suite includes cross-process races, failure injection, parser round trips, history recovery, shutdown admission and all 26 original review mappings.
- Separate safety probes: **12 tests passed**. Repeated retirement, missing personal parents, collision refusal, stale saves, preserving external edits, frontmatter quoting, history path validation and tail recovery, personal Markdown links, slash-containing titles and literal shell filenames.
- Separate HTTP acceptance: **28 checks passed**. Creation, preview without saving, edit conflict, section editing, promotion, history/diff, retirement twice, restoration to the inbox, CSRF/Origin/Host rejection, special pages, and `--no-check`.
- Actual Chrome via Playwright: light default despite a dark OS preference, persisted explicit theme choice, `/` search focus, delayed suggestions staying dismissed after Escape/clear/outside click, preview and save through real HTML form navigations, and a 390px viewport without horizontal overflow or JavaScript errors.
- Actual TCP port migration: the original bound port remains valid after configuration reload; the CLI finds that server, restarts it on the new port and stops it even before the original parent reaps the old process.
- Actual TCP shutdown: SIGTERM waits for an admitted mutation and its history write, without waiting for an idle connection.
- Forced process exit during lifecycle move: the next inventory read recovers exactly one authoritative card with content intact.
- Injected source-unlink failure: the destination is rolled back and the original card remains unchanged.
- SIGINT during a detached check: descendants cannot perform delayed side effects after cancellation.
- CRLF history: revision rendering parses metadata correctly and restore reproduces the original bytes exactly.
- Concurrent read during a lifecycle move: the reader waits for the transaction and sees only one card.
- Additional randomized parser probe: **3,000 scalar/list/body round trips passed**.
- Existing-data compatibility: **38 real cards retained their byte hashes and interpreted metadata**, and all **40 existing history revisions** parsed successfully. This was a read-only compatibility check.
- Design-system checker passed for `src/atlas_cli/wiki/shell.html`: 37 colors, two themes, 12 contrast pairs. Desktop and phone screenshots were inspected.

The real-browser tests caught `Origin: null` caused by `Referrer-Policy: no-referrer`; the fixed same-origin policy retains strict cross-origin rejection. The real-process tests caught the stopped-but-unreaped PID issue; the fixed stop path uses the exact server instance's post-drain completion marker.

## Boundaries

These are local automated and browser acceptance results, not hosted CI. Atlas still executes trusted, user-authored check commands; it is not a command sandbox. Inventory locks coordinate Atlas processes, not arbitrary external editors. Recovery fails closed when journaled files have changed identity or content. SIGKILL cannot gracefully drain an active request. The backup taken before deployment is retained separately on the user's machine.
