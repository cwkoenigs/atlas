# Second-review resolution

Scope: all seven findings from the fresh review of `84a3e6f`. Every listed test exists in the final candidate. No finding is intentionally deferred.

## 1. P1 — Ordinary saves preserve concurrent external edits

Save intent is journaled; exclusive capture preserves and validates the actual displaced inode. Publication, rollback and recovery retain unknown edits instead of overwriting them.

Regressions:
- `tests.test_review2_save.SaveTests.test_claim_and_publication_races_preserve_unknown_files`
- `tests.test_review2_save.SaveTests.test_external_atomic_save_after_history_is_preserved`
- `tests.test_review2_save.SaveTests.test_open_descriptor_edits_remain_in_claim_after_save`
- `tests.test_review2_save.SaveTests.test_process_reader_waits_until_save_published`
- `tests.test_review2_save.SaveTests.test_publication_failure_restores_preimage`
- `tests.test_review2_save.SaveTests.test_rename_failure_rolls_back_and_readers_wait`
- `tests.test_review2_save.SaveTests.test_save_crash_matrix_and_exact_restore`
- `tests.test_review2_save.SaveTests.test_save_recovery_path_and_identity_validation_fail_closed`

## 2. P1 — Private form edits and visibility changes are atomic

The edited body is staged in its final personal destination and committed as one save/move transaction. A failure leaves the shared source preimage intact, without submitted private text.

Regressions:
- `tests.test_review2_personal.PersonalTests.test_personal_collision_refuses_without_writes`
- `tests.test_review2_personal.PersonalTests.test_personal_crash_matrix_and_git_ignore`
- `tests.test_review2_personal.PersonalTests.test_private_body_never_published_in_shared_card`
- `tests.test_review2_personal.PersonalTests.test_rename_failure_keeps_shared_preimage`

## 3. P2 — Check outcomes belong to the current command and run

Command/snapshot fingerprints and cross-process generations reject obsolete outcomes. Wiki and CLI validate current results; progress callbacks cannot print discarded success, and missing outcomes are not counted as all OK.

Regressions:
- `tests.test_review2_checks.CheckTests.test_blocked_permissions_preserve_matching_result`
- `tests.test_review2_checks.CheckTests.test_changed_deleted_and_stale_explicit_snapshot`
- `tests.test_review2_checks.CheckTests.test_explicit_check_does_not_return_prior_success_after_command_edit`
- `tests.test_review2_checks.CheckTests.test_legacy_cache_and_edited_command_never_display_ok`
- `tests.test_review2_checks.CheckTests.test_old_command_cannot_overwrite_new_result`
- `tests.test_review2_checks.CheckTests.test_same_command_older_run_cannot_replace_newer_commit`
- `tests.test_review2_cli.CheckReportingTests.test_card_view_hides_changed_command_passing_result`
- `tests.test_review2_cli.CheckReportingTests.test_card_view_hides_legacy_passing_result`
- `tests.test_review2_cli.CheckReportingTests.test_card_without_command_is_not_counted_as_checked`
- `tests.test_review2_cli.CheckReportingTests.test_empty_inventory_reports_nothing_to_check`
- `tests.test_review2_cli.CheckReportingTests.test_explicit_check_reports_discarded_outcome_as_not_checked`
- `tests.test_review2_cli.CheckReportingTests.test_genuine_current_failure_is_reported_as_failure`
- `tests.test_review2_cli.CheckReportingTests.test_genuine_current_pass_is_reported_as_success`
- `tests.test_review2_cli.CheckReportingTests.test_newer_failure_is_printed_instead_of_old_callback_success`

## 4. P2 — Unicode separators cannot poison frontmatter

Metadata uses physical LF boundaries, unusual separators roundtrip, and serialized cards are validated before publication.

Regressions:
- `tests.test_review2_unicode.UnicodeTests.test_inspect_draft_load_unicode_package_description`
- `tests.test_review2_unicode.UnicodeTests.test_invalid_serializer_never_publishes_new_card`
- `tests.test_review2_unicode.UnicodeTests.test_legacy_unicode_plain_comment_and_crlf`
- `tests.test_review2_unicode.UnicodeTests.test_separator_scalar_list_and_body_roundtrip`

## 5. P2 — Historical aliases cannot take an existing name

The entire candidate title/alias namespace is checked under the inventory lock against other titles, aliases, slugs and IDs before any mutation.

Regressions:
- `tests.test_review2_aliases.AliasTests.test_restore_refuses_alias_now_owned_by_other_card`
- `tests.test_review2_aliases.AliasTests.test_unchanged_title_alias_collision_with_each_namespace`
- `tests.test_review2_aliases.AliasTests.test_unique_rename_keeps_old_alias_case_insensitive`

## 6. P3 — Git revision restore preserves exact bytes

Git blobs are captured as bytes and decoded without universal-newline translation; CRLF and missing final newlines survive restoration.

Regressions:
- `tests.test_review2_git.GitRevisionTests.test_git_crlf_revision_render_and_restore_exact_bytes`

## 7. P3 — Simultaneous wiki startup is coordinated

A separate reentrant cross-process lifecycle lock serializes discovery/start/stop/restart and waits for a verified listener, without holding the inventory lock during drain.

Regressions:
- `tests.test_review2_lifecycle.LifecycleTests.test_direct_start_and_wait_false_adopt_verified_listener`
- `tests.test_review2_lifecycle.LifecycleTests.test_health_does_not_adopt_wrong_instance_from_old_port`
- `tests.test_review2_lifecycle.LifecycleTests.test_identity_validation_and_foreign_occupant`
- `tests.test_review2_lifecycle.LifecycleTests.test_independent_processes_serialize_start_and_restart`
- `tests.test_review2_lifecycle.LifecycleTests.test_probe_does_not_relabel_wrong_reported_port`
- `tests.test_review2_lifecycle.LifecycleTests.test_restart_does_not_hold_inventory_lock_while_draining`
- `tests.test_review2_lifecycle.LifecycleTests.test_simultaneous_threads_start_only_one_server`

## Verification

The full repository suite passed **119 tests**. The parent separately passed nine acceptance tests, including actual simultaneous CLI startup on a disposable loopback port; real Chrome forms and search, 28 HTTP acceptance checks, port migration, graceful drain, cancellation and crash/recovery probes also passed. All 38 live card hashes and parsed metadata matched in a read-only compatibility check. See `review2-parent-verification.md` and `review2-cli-red-green.md`.

The first independent fix review found two remaining CLI result-reporting gaps; those are included in finding 3 and covered by eight focused CLI tests. Final production hashes are checked against the frozen follow-up review before merge.

## Limitations

User-authored check commands are trusted executable code. Legacy results without command/snapshot bindings intentionally display as not checked until rerun. Advisory locks coordinate Atlas processes, while unknown external edits are preserved in ignored recovery claims; conflicting recovery can require reconciliation. Linux-specific system calls and physical power-loss durability were not exercised on this macOS host.
