# PSI CI — Local Run Record (12E-PSI-CI-EXEC-001)

Scope: local preparation only. NOT pushed. NOT enabled. Workflow `.github/workflows/psi-ci.yml` has never run on GitHub.
Base: `07f0672` (Phase 1 accepted). Lock files unchanged. PSI business logic and migrations unchanged.

## Local regression results (this revision)

| Suite | Command scope | Result |
|---|---|---|
| SQLite | isolated branch (PSI-1..3 only), `APP_TEST_DATABASE_URL` unset | 152 passed, 7 skipped (all PostgreSQL-only), exit 0 |
| PostgreSQL 17 | isolated branch (PSI-1..3 only), disposable DB; JUnit gate `--max-skipped 0` | **159 passed, 0 skipped, 0 failed, gate exit 0** |
| Concurrency (PostgreSQL) | `tests/test_psi_concurrency_pg.py`, 5 repeated runs | 4 passed each run |
| Control (negative) | pause disabled | 1 failed, 1 error, exit 1 (in 18 s; no hang) |

SQLite skips (7) are PostgreSQL-only by design: 2 in `test_postgres_smoke.py`, 5 in `test_psi_concurrency_pg.py`. The 0-skipped requirement applies to the PostgreSQL job, which is where CI checks it.

Scope: this isolated branch excludes PSI-4 (operator authorization), PSI-5 (pseudonym, key rotation, empty-actor audit) and their tests (`test_psi_authz.py`, `test_psi_log_leak.py`). PG floor in CI set to 159 (measured). Concurrency suite: 5 tests, all pass on PG.

Scratch PostgreSQL is local engineering evidence only. It is not staging or production evidence.

## Concurrency tests: what they prove and what they do not

Four scenarios, each synchronised at an exact commit boundary by a SQLAlchemy `before_commit` hook on one session only. No production code is modified.

1. `claim_held_then_duplicate_returns_in_progress_then_original_accepts` — duplicate arriving while the first claim is in Phase C returns `IN_PROGRESS`; the original returns `ACCEPTED`; one ledger row.
2. `duplicate_after_original_commit_returns_duplicate_with_original_prospect` — sequential by design; verifies `DUPLICATE` with the original prospect id.
3. `stale_claim_resolves_to_reconcile_and_is_not_retried` — see finding F1 below.
5. `duplicate_loses_at_unique_constraint_and_resolves_to_duplicate` — true race. Measured, not inferred: A is held after its claim INSERT is flushed (`after_flush`); B blocks on the unique index (synchronised by polling `pg_stat_activity` for a Lock wait, no fixed sleep); A is released and commits; B raises `IntegrityError` (counter = 1, asserted); B returns `IN_PROGRESS / claim_in_flight`. Passed 3/3. Note: the original `before_commit` hook was wrong because SQLAlchemy sends the INSERT during commit, after that hook.
4. `phase_c_failure_rolls_back_and_marks_reconcile` — fault injection in the prospect write.

Verified control: with the pause disabled, scenario 1 fails and does not pass by chance.

Outcome of the true race is `IN_PROGRESS`, not `DUPLICATE`, because the original claim was still in Phase C. `DUPLICATE` is covered by scenario 2 (post-commit). The PSI-5 gap is therefore closed for the constraint path only.

## Findings (open, for Director review — no production code changed)

**F1. Stale RECEIVED claim is reported as RECONCILE but not persisted.**
`_resolve_existing` returns `RECONCILE / outcome_unknown` for a claim older than `IN_FLIGHT_WINDOW_S`, but does not write `RECONCILE` to the row. The row stays `RECEIVED`. Effects: the operator has no persistent signal from the row itself; a later reader sees `RECEIVED` and may treat it as in-flight. The test asserts the observed behaviour and does not hide it. Director decision needed: persist `RECONCILE` on stale detection, or keep it as is.

**F2. Claim age uses the real clock, not `now_epoch`.**
`_resolve_existing` uses `_now()` (wall clock). Tests that use the fixed synthetic `NOW` must set claim timestamps against the real clock. Test-only consequence; recorded so future tests do not repeat the mistake.

**F3. Test isolation.**
The concurrency tests call `drop_all` and `create_all` on the database named by `APP_TEST_DATABASE_URL`. They must only ever point at a disposable database. The CI job uses a service container; local use must point at a scratch database.

## CI workflow — what was verified and what was not

Verified locally:
- YAML parses. 6 jobs. `permissions: contents: read`. No `pull_request_target` trigger.
- Every `uses:` action is pinned to a full 40-char commit SHA (verified: tag -> commit, 14 occurrences, 0 unpinned).
- PostgreSQL service image pinned to `postgres:17@sha256:87c8b42f423b45d5247e6aa8fdb2e7762fec164c68a50fe3eb07e7bfcaf4dbcf` (Docker Hub official library manifest, read-only registry query).
- Service ports bound to loopback: `127.0.0.1:5432:5432` (3 jobs).
- No `secrets.` references remain. Service PostgreSQL password is an ephemeral, non-secret constant that exists only inside the runner's service container.
- Fork PRs: `lock-check`, `secret-scan`, `sqlite-fast` run. `pg-required`, `migration-gate`, `concurrency-regression` are gated to same-repository PRs and pushes.
- Artifacts: three JUnit XML reports only. Retention 14 / 14 / 30 days.
- gitleaks checksum for `gitleaks_8.30.1_linux_x64.tar.gz` taken from the upstream checksums file: `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`.

NOT verified (blocking before the workflow can be trusted):
- **B-CI-1: CLOSED.** Digest pinned (see above).
- **B-CI-2: Workflow never executed on GitHub.** Local YAML and structure checks are not a substitute for a run. Needs a sandbox branch run after Director approval to push.
- **B-CI-3: CLOSED.** All actions pinned to full SHA.
- **B-CI-4: CLOSED (local).** `migration-gate` runs upgrade head, downgrade -1, upgrade head on an empty database. Verified locally on a throwaway DB (exit 0 x3, current = head). NOTE: `b8c9psi03hardening` downgrade DROPS tables and columns (`psi_source_secrets`, `psi_permission_evidence`, provenance columns). It is safe only on an empty throwaway database and must never be run against any database with data.
- **B-CI-5: CLOSED.** Skip and failure validation now uses `backend/scripts/ci_junit_gate.py` on the JUnit XML. Tested on 5 cases: real PG report (exit 0), report with a skip (exit 1), corrupt XML (exit 2), missing file (exit 2), tampered totals (exit 2). Grep for SKIPPED removed.
- **B-CI-6: Fork-PR behaviour** not tested on a real fork.

## Files in this revision

- `backend/tests/test_psi_concurrency_pg.py`: deterministic barrier tests, now 5 scenarios including the unique-constraint race.
- `backend/scripts/ci_junit_gate.py` (new): fail-closed JUnit validator.
- `.github/workflows/psi-ci.yml` (new): local workflow, not pushed, not enabled.
- `docs/ai/PSI_CI_LOCAL_RUN.md` (new): this record.

No changes to `backend/app`, `backend/migrations`, `backend/requirements*`, `.gitleaks.toml`, or `.pre-commit-config.yaml`.

## Stop point

Local commit only. Push, PR, branch protection, and enabling the workflow require separate Director approval, and blockers B-CI-1 and B-CI-2 must be cleared first.
