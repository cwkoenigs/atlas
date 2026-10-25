# Codex review resolution

Scope: all 26 findings from the review of baseline `728682f` (5 P1, 20 P2, 1 P3). Fixes are confined to the isolated `fix/codex-review` checkout. No live inventory, installed tool, remote, skill, or life-admin output is modified or published.

The adjacent JSON map is validated by the automated suite: it must contain exactly findings 1–26 and every named regression must be discoverable. The observed red/green steps are in [regression-log.md](regression-log.md). Supplemental concurrency/fault-injection cases strengthen already reproduced fixes.

| # | Review title | Fix | Automated regressions |
|---|---|---|---|
| 1 | **[P1] Reject retirement of an already-retired card** | Retirement returns the existing retired path without rewriting or unlinking it. | `tests.test_review.ReviewTests.test_01_repeat_retire` |
| 2 | **[P1] Quote scanned paths as literal shell arguments** | Scan commands use shlex.quote on resolved absolute paths; executable and argument remain separate shell tokens. | `tests.test_review.ReviewTests.test_02_literal_scan_paths` |
| 3 | **[P1] Refuse to overwrite another card during moves** | Lifecycle moves validate source snapshots and refuse destination collisions under the inventory lock; wiki edit/share checks the destination before saving. | `tests.test_review.ReviewTests.test_03_lifecycle_collisions`<br>`tests.test_review.ReviewTests.test_03_edit_share_collision_is_unchanged` |
| 4 | **[P1] Make card updates transactional across CLI and wiki** | Shared reentrant flock/RLock transactions, exact raw preimage validation, locked inventory reads, atomic fsync/replace writes, and friendly CLI/HTTP conflicts. | `tests.test_review.ReviewTests.test_04_stale_process_and_atomic_save`<br>`tests.test_review.ReviewTests.test_04_simultaneous_writers`<br>`tests.test_review.ReviewTests.test_04_promotion_rejects_edit_during_check`<br>`tests.test_review.ReviewTests.test_04_load_serializes_with_lifecycle_move`<br>`tests.test_review.ReviewTests.test_04_cli_reports_safe_conflicts`<br>`tests.test_review.ReviewTests.test_04_wiki_and_cli_race`<br>`tests.test_review.ReviewTests.test_04_atomic_replace_failure_preserves_file` |
| 5 | **[P1] Preserve the current external version before every mutation** | ensure_base compares every on-disk preimage with the last history text before any supported mutation. | `tests.test_review.ReviewTests.test_05_external_preimage`<br>`tests.test_review.ReviewTests.test_06_raw_crlf_preimage` |
| 6 | **[P2] Make frontmatter encoding and parsing lossless** | In-memory quote-aware parsing and symmetric JSON string/list encoding retain quotes, commas, comments, backslashes, whitespace, and line endings; legacy plain/comment cards remain readable. | `tests.test_review.ReviewTests.test_06_frontmatter_roundtrip`<br>`tests.test_review.ReviewTests.test_06_raw_crlf_preimage`<br>`tests.test_review.ReviewTests.test_06_plain_apostrophe_comments` |
| 7 | **[P2] Validate card IDs before constructing history paths** | History path construction validates the documented ID format and checks resolved path containment, including symlinks. | `tests.test_review.ReviewTests.test_07_history_ids` |
| 8 | **[P2] Repair unterminated history tails before appending** | Locked atomic history replacement preserves valid unterminated entries and quarantines incomplete tails, including partial UTF-8; complete corrupt records and invalid writer fields fail closed. | `tests.test_review.ReviewTests.test_08_history_tails`<br>`tests.test_review.ReviewTests.test_08_history_concurrent_append`<br>`tests.test_review.ReviewTests.test_08_partial_utf8_tail_is_quarantined`<br>`tests.test_review.ReviewTests.test_08_history_invalid_entry_rejected` |
| 9 | **[P2] Parse revision text without a shared temporary file** | Revision rendering uses core.parse_text in memory and never writes rev.md. | `tests.test_review.ReviewTests.test_09_revision_in_memory` |
| 10 | **[P2] Merge check results atomically across processes** | Checks run outside the inventory lock, then merge only accepted updates into fresh state atomically; blocked wiki results never enter the commit. | `tests.test_review.ReviewTests.test_10_check_process_merge`<br>`tests.test_review.ReviewTests.test_10_blocked_check_keeps_concurrent_success` |
| 11 | **[P2] Bind edit conflict tokens to the rendered snapshot** | The edit token is derived from the parsed card's retained raw snapshot; conflict checking and saving occur under the common transaction lock. | `tests.test_review.ReviewTests.test_11_rendered_snapshot_token` |
| 12 | **[P2] Drain active mutations before stopping the server** | Server admission tracks accepted mutations and snapshot history-sync writes, rejects new writers when stopping, and drains accepted writers without waiting for idle request readers. | `tests.test_server.ServerTests.test_12_shutdown_drains_mutation_ignores_idle`<br>`tests.test_server.ServerTests.test_12_shutdown_drains_get_history_sync`<br>`tests.test_server.ServerTests.test_12_no_new_history_writers_after_shutdown` |
| 13 | **[P2] Create parent directories for personal-card destinations** | All lifecycle/new-card destination directory creation includes parents=True. | `tests.test_review.ReviewTests.test_13_personal_parent_directories` |
| 14 | **[P2] Preserve comma-containing titles in related-page forms** | Related-page form values retain stable IDs; complete comma-containing titles resolve before CSV parsing, with quoted CSV names supported. | `tests.test_review.ReviewTests.test_14_related_comma_title` |
| 15 | **[P2] Reject title collisions when renaming pages** | A locked fresh namespace check rejects title/alias/ID/slug ownership collisions on saves, renames, creation, and historical restore; unique renames retain the old title as an alias. | `tests.test_review.ReviewTests.test_15_rename_collision`<br>`tests.test_review.ReviewTests.test_15_restore_rejects_name_collision` |
| 16 | **[P2] Terminate check descendants when a timeout expires** | Each check starts a process group; timeout, cancellation, and communication failures send group TERM followed by bounded group KILL and reap the shell. | `tests.test_review.ReviewTests.test_16_check_process_group_timeout` |
| 17 | **[P2] Validate requests against the server's bound port** | Host/Origin checks and health responses use server_port, not mutable config. Socket-bound metadata enables old-port discovery, restart, and stop; stop accepts only process exit or an instance-bound post-drain/post-close marker and reports drain timeout accurately. | `tests.test_server.ServerTests.test_17_bound_host_and_origin`<br>`tests.test_server.ServerTests.test_17_discover_old_port_restart_and_stop`<br>`tests.test_server.ServerTests.test_17_cli_stop_reports_drain_timeout` |
| 18 | **[P2] Honor the no-check option before executing commands** | --no-check prevents automatic and explicit --check execution on both map and today. | `tests.test_review.ReviewTests.test_18_no_check_precedence` |
| 19 | **[P2] Handle empty inventories and scan results** | Display width calculations use defaults for empty active inventories and empty scan results. | `tests.test_review.ReviewTests.test_19_empty_inventory_and_scan` |
| 20 | **[P2] Split editor commands into executable and arguments** | EDITOR is split with shlex.split; the card path is appended as a distinct argument. | `tests.test_review.ReviewTests.test_20_editor_arguments` |
| 21 | **[P2] Seed the interactive new-card form from supplied flags** | Every interactive field is initialized from parsed flags and --link survives form submission. | `tests.test_review.ReviewTests.test_21_interactive_flags` |
| 22 | **[P2] Bound directory traversal before materializing file paths** | A lazy file iterator is capped with islice before Path-list materialization and prunes dependency/cache directories. | `tests.test_review.ReviewTests.test_22_bounded_scan_traversal`<br>`tests.test_review.ReviewTests.test_22_prunes_dependency_trees` |
| 23 | **[P2] Retain personal directories in generated Markdown links** | Markdown targets derive from the complete root-relative card path with only the extension removed. | `tests.test_review.ReviewTests.test_23_personal_markdown_links` |
| 24 | **[P2] Associate recent Git changes across filename renames** | Recent events use per-card git log --follow, retaining association through multiple filename renames. | `tests.test_review.ReviewTests.test_24_recent_changes_follow_renames` |
| 25 | **[P2] Resolve complete page names before stripping path prefixes** | Resolution tries the complete name first and only strips a recognized cards/inbox/retired path prefix as a fallback. | `tests.test_review.ReviewTests.test_25_complete_slash_page_names` |
| 26 | **[P3] Invalidate pending suggestions when dismissing search** | Clear/Escape/outside dismissal invalidate sequence tokens and pending timers; responses recheck sequence after fetch and after JSON completion. | `tests.test_review.ReviewTests.test_26_suggestion_cancellation` |

## Remaining independent merge gates

The fresh follow-up fix pass implements only the six gates in the parent handoff. New tests live in `tests.test_followup.FollowupTests`; names below refer to methods on that class unless qualified. The initial 11-test run failed before implementation with the observed header, duplicate-card, unreaped-PID, SIGINT side-effect, and CRLF failures. The expanded suite contains 19 tests; additional cases cover recovery boundaries and fail-closed behavior. The staging-time source replacement regression was also observed red before its identity-capture fix.

| Gate | Cause and resolution | Regressions |
|---|---|---|
| 1. Browser forms | `no-referrer` hides Chrome's form origin. Responses now use `same-origin`; Origin:null still returns 403. | `test_form_referrer_policy_and_strict_origin`; existing `tests.test_server.ServerTests.test_17_bound_host_and_origin` |
| 2. Unreaped stopped server | PID existence cannot distinguish an active writer from a zombie. Health and metadata share a random instance ID; a completion marker is written only after drain and listener close. Stop checks that exact identity and retains the PID-exit fallback. | `test_stop_completed_identity_marker_without_pid_reap`, `test_stop_rejects_foreign_marker_and_health_loss`, `test_shutdown_marker_only_after_drain_and_close`; existing bound-port migration and drain-timeout tests |
| 3. Duplicate move cards | Destination publication previously preceded an unprotected unlink. Moves journal exact before/after text and source/staging inode identities, publish exclusively with a staging hard link, claim source and rollback destination via atomic exclusive rename, retain captured inodes, and recover on inventory reads, mutations, and wiki startup. History completion is idempotent. | `test_move_claim_failure_rolls_back`, `test_move_interruption_recovered_on_inventory_read`, `test_move_interruption_before_destination`, `test_move_interruption_after_history_is_idempotent`, `test_move_refuses_source_replaced_during_staging`, `test_move_recovery_refuses_replaced_source`, `test_move_recovery_refuses_replaced_destination`, `test_move_recovery_refuses_edited_source`, `test_move_recovery_refuses_edited_destination`, `test_move_recovery_refuses_partial_journal`, `test_move_recovery_refuses_escaping_journal`; existing lifecycle collision and locked-load tests |
| 4. Cancelled checks | Only timeout handled detached descendants. `BaseException` during communication now terminates the process group, reaps the direct child, and re-raises. | `test_check_sigint_cancels_descendants`, `test_check_communication_failure_cancels_descendants`; existing timeout regression |
| 5. CRLF wiki revisions | LF-only validation remained in revision rendering and restore. Both now use `core.parse_text`; restore writes the untouched revision string. | `test_crlf_revision_render`, `test_crlf_revision_restore_exact_bytes`; existing raw CRLF preimage regression |
| 6. Stale-token writes during drain | Already fixed in supplied WIP: invalid-token POSTs use admitted `_snapshot()` and handle `Stopping`. No implementation change needed. | `tests.test_server.ServerTests.test_12_no_new_history_writers_after_shutdown` checks both current and stale tokens and unchanged history |

The supplied WIP also already locks `load()` across moves and rejects restore title collisions. `tests.test_review.ReviewTests.test_04_load_serializes_with_lifecycle_move` and `test_15_restore_rejects_name_collision` remain green; the independent parent read-lock probe also passes this final implementation.

## Verification boundaries

- All Python tests use isolated TemporaryDirectory inventories under TMPDIR; child check working directories are set to their fixture root before checks run. No existing real card commands execute.
- Real subprocess races cover card writers, wiki-versus-CLI actions, check-result merging, blocked-result preservation, and concurrent history recording. Git rename checks use a disposable Git repository with fixture identity.
- The Node harness executes the shipped search script against controlled DOM events and fetch/JSON promises: six combinations of fetch-versus-JSON completion and clear/Escape/outside dismissal.
- TCP binding is denied by the execution sandbox (`PermissionError: [Errno 1] Operation not permitted`). HTTP tests use real socket pairs with listener binding disabled, actual handler threads, controlled signal callbacks, and controlled health endpoints. A live TCP start/stop smoke test remains an environment limitation.
- Atlas locks are advisory and local to one machine. Source removal and destination rollback now use atomic exclusive rename, followed by validation of the actual captured inode and text. Claims and staging files remain durable backups, preserving writes through open file descriptors. Exclusive hard-link restoration never overwrites a recreated original name. Conflicting/changed artifacts and partial/older/rollback journals block inventory reads with a reconciliation error; retain all artifacts for manual comparison. Backups consume space and have no automatic cleanup. macOS exclusive rename is exercised here; Linux renameat2 support is implemented but was not run on this macOS host. Unsupported rename/filesystem operations fail closed. This is not multi-file ACID for outside writers. Graceful shutdown is covered; SIGKILL cannot drain.

## Final checks

The exact final command, totals, and compileall result are recorded in [validation.md](validation.md). No review finding is intentionally deferred.

## Final P1: external-editor removal race

The last independent blocker was a source-name TOCTOU after destination publication. Version-2 intent records private source/destination claims before mutation. Normal moves and recovery share the same claim/validate/retain protocol, including ownership-safe rollback. Source permissions survive capture and are copied to the published stage. A successful move retains `.atlas-claim-*/source`; rollback retains `.atlas-claim-*/destination`. No captured card inode is unlinked after validation, so late edits through open descriptors survive. Pending rollback fails closed after a crash instead of replaying forward. See the README for manual recovery semantics.

Exact regressions on `tests.test_move_claim.MoveClaimTests` (also mapped to finding 4 in the JSON map):

- `test_atomic_editor_after_destination_publication`
- `test_recovery_atomic_editor_after_destination_publication`
- `test_source_replaced_before_claim`
- `test_claim_replaced_after_rename`
- `test_rollback_never_overwrites_new_original`
- `test_original_created_after_claim_is_preserved`
- `test_rollback_claims_replaced_destination_without_deleting_it`
- `test_open_fd_edit_after_claim_validation_keeps_inode`
- `test_crash_after_claim_before_history_recovers`
- `test_claim_path_cannot_escape_inventory`
- `test_claim_occupied_at_rename_is_never_overwritten`
- `test_recovery_retains_changed_claim_for_reconciliation`
- `test_reader_waits_while_source_is_claimed`

Existing failure/crash tests in `tests.test_followup` now inject at `A._rename_claim`, before and after the actual atomic capture; their rollback, fresh-process recovery, single-card and idempotent-history assertions remain intact. No previous test was dropped.
