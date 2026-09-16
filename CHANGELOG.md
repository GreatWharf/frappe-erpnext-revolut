# 0.5.0 — Broader compatibility and clearer daily controls

Release candidate dated 2026-09-16. Existing tags are unchanged.

- Support matching Frappe/ERPNext v15 and v16 on MariaDB. Restore Python 3.10-compatible syntax, add a v15 Workspace fallback, and retain native v16 navigation.
- Persist explicit account exclusions. Import selected FX/transfer legs when their counterpart was intentionally skipped, while continuing to flag genuinely unknown accounts for review.
- Preserve source/audit identity and paused-account history. Adapt long reference text to older v15 Data fields without truncating the stored source payload.
- Keep Sync now, Bank transactions, Reviews and Sync logs prominent. Organize secondary dashboard actions into Sync options and Extra data, with account management/pause separated and confirmed.
- Group connection-form actions and hide sync commands that are unavailable while paused.
- Hold configuration locks until commit/rollback, and persist API writes before releasing the connection lock. Token-refresh commits do not release active worker locks.
- Include setup logos in wheel/source distributions and verify every runtime file in both archives.
- Add Python 3.10/3.12/3.14 unit CI and real Frappe v15/v16 installation/migration/integration jobs on release branches and tags.

**Upgrade:** Back up the database, private files and encryption key; update the app; run migration and your deployment's normal asset rebuild/restart. Older omitted mappings are not automatically inferred as intentional skips. Reopen account management and save your selections to record explicit exclusions. Review/backfill older held transactions after confirming those choices.

See [compatibility](docs/v16-compatibility.md) and [verification](docs/verification.md). Check the exact release commit's CI and staging acceptance before production use. A tag is not Marketplace approval or live-bank certification.

# 0.4.4 — Frappe Cloud Marketplace metadata

- Declare Frappe v16 compatibility in `pyproject.toml` for Frappe Cloud validation.

# 0.4.3 — Account identification and optional mapping

- Show account names, balances, status, available type, full ID and timestamps during mapping.
- Label missing or UUID-only names as unnamed; preserve Revolut-provided details without guessing account categories.
- Skip unfamiliar accounts and start with only the accounts you choose.
- Save setup for later with all new accounts skipped, without starting sync.
- Reopen mapping from the dashboard with **Manage accounts (pauses sync)**.
- Keep existing mappings, encrypted-credential fixes, Home navigation and branding.

# 0.4.0 — Frappe / ERPNext v16

- Targets Frappe/ERPNext v16 with Python 3.14.x, Node 24 and v16 runtime/build examples; v15 retains the separate 0.3 package.
- Updated Desk links to /desk, registered the v16 app icon with explicit role permission, and aligned DocType default sorting.
- Migrated bench tests to IntegrationTestCase and explicit test record dependencies.
- Added CLI-only idempotent site initialization and a deploy-job fragment, avoiding manual installation commands or a required GitHub Actions workflow.
- Added version-gate, runtime, first-install bootstrap and repeat-install regression tests; verified local suite on Python 3.14.

# 0.3.0

- Routine polling uses a configurable 60-minute overlap; a separate daily recent-history check retains seven-day correction coverage.
- Hourly account/balance snapshots and optional independently scheduled expense, receipt, FX and accounting-reference imports.
- Expense pagination/checkpoints, historical audits, individual rechecks, stable upserts and isolated receipt retry queue.
- Private size-limited receipts, explicit invoice/claim links and review flag for changed linked evidence.
- Daily FX quotes with explicit Currency Exchange adoption and no existing-rate overwrite.
- Original bill amounts/currencies and effective bill conversion rate on standard Bank Transactions.
- Frontend feature selection, evidence views, upgrade/coverage guide and regression tests.

# 0.2.0

- Guided native ERPNext setup page with server-generated certificate, read-only consent, account discovery/mapping and sync controls.
- Public certificate copy data only; private keys remain encrypted on the server.
- Manual GitHub image build and self-hosted Docker browser deployment instructions.
- Certificate and pasted authorization URL validation tests.

# Changelog

## 0.1.0 — 2026-09-12

Initial release candidate for Frappe/ERPNext v15: READ-only Revolut Business connection, encrypted OAuth refresh, account/currency mapping, standard Bank Transaction imports, durable source ledger, resumable synchronization, historical backfill/audit, safe change review, signed webhook inbox, tests and deployment documentation.
