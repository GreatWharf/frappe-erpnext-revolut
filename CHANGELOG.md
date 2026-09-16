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
