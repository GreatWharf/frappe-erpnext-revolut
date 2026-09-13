# Operations and troubleshooting

## Routine monitoring

Check Revolut Connection's Last Attempt, Last Success, Last Status, Last Error Code and Poll Cursor. A successful run can still be catching up through historical windows; compare Poll Cursor to current time. A Review Required result means API retrieval succeeded but at least one source needs attention. Inspect the connection's Source Reviews and Sync Logs. Review count in a log counts observations in that run, not unique unresolved cases.

The worker catches errors into the durable Sync Log and connection status rather than storing a potentially sensitive Python traceback in RQ. Consequently, RQ can report a completed job whose application status is Error. Monitor application status and stale Last Success, not only RQ failures. Configure your existing operational monitor to alert when Last Success is stale beyond your recovery objective, when Error persists, or when source reviews accumulate. The app does not email anyone automatically.

A hard-killed job can leave a Running log; daily maintenance marks runs older than 30 minutes Interrupted. Check process/OOM logs and enqueue again. The Redis lock lasts 960 seconds, longer than the 900-second worker timeout; avoid increasing worker timeout without also reviewing the lease and workload budget.

## Scheduler and workers

The scheduler registers a 15-minute cron hook on install/migrate. It needs an active scheduler process and a worker consuming `long`. On Bench:

```bash
bench --site SITE enable-scheduler
bench doctor
bench --site SITE list-apps
```

Check the Scheduled Job Type for `revolut_bank_feed.sync.schedule`, the Background Jobs queue, and the worker logs. Migrate after changing hooks. Manual Sync Now also needs the worker. A durable webhook does not need the worker to be healthy at receipt time, but cannot import until workers recover. Redis queue loss does not erase source data or accepted webhook events; the scheduler requeues work.

## Common diagnostic codes

| Code/status | Meaning and next action |
| --- | --- |
| connection_busy | Another sync/auth action owns the lock. Wait for it to finish; repeated jobs are deduplicated. |
| authorization_required / missing_refresh_token | Complete the READ consent and code exchange. |
| token_http_400 / token_http_401 | Check code expiry, certificate/client/issuer, revoked consent and server time; reauthorize as needed. |
| token_network_error_reauthorize_if_needed | Token response was lost. The remote grant may have succeeded; retry refresh or repeat consent if needed. |
| invalid_base64_private_key / invalid_signing_key | Load the matching unencrypted RSA PEM key using the form action; never upload a public certificate in its place. |
| unexpected_token_scope_revoke_consent | Revoke the broad grant and use the app's READ consent URL. |
| revolut_http_401 / revolut_http_403 | Check certificate/consent, API access and IP allowlist. A 401 is refreshed once, never in an infinite loop. |
| revolut_http_429 / revolut_rate_limit_retry_later | Server rate limit persists or requests a long delay. Leave the scheduler to retry; reduce traffic/window sizes if sustained. |
| revolut_network_error / revolut_http_5xx | Check network/API availability. Progress is retained and retry is safe. |
| no_account_mappings | Discover accounts and configure maps while the connection is disabled. |
| mapped_account_missing_in_revolut | Wrong environment/certificate/account ID, or retired account. Verify discovery; pause obsolete maps if appropriate. |
| unmapped_account_or_currency | Map each involved account/currency, then re-fetch or backfill. No partial FX import is accepted. |
| mapping_company_mismatch / mapping_currency_mismatch | Bank Account/ledger no longer matches the pinned Company/currency. Correct setup; do not convert by changing import numbers. |
| transaction_account_currency_mismatch | Upstream leg differs from the account currency. Review the source with Revolut rather than substituting bill_amount. |
| fee_policy_review_required | Compare statement evidence, set the mapping's fee policy while disabled, then review/replay. |
| upstream_financial_or_state_change | Source evidence differs from an imported row; use the review procedure below. |
| paused_map_has_unresolved_review | Re-enable that map and resolve its earlier conflict. |
| remove_reconciliation_links_before_review | An affected Bank Transaction has payment links/allocation. An accountant must remove them before applying the source change. |
| bank_amount_precision_or_schema_mismatch | ERPNext changed imported monetary/date/currency values. Check currency precision and custom document hooks; do not bypass the guard. |
| pagination_tie_saturated | ≥1,000 items share an exact timestamp; no reliable API tie cursor is documented. Preserve the checkpoint and investigate with Revolut support. |
| pagination_page_limit / job_time_budget | Large window hit a work bound. The next run resumes after the last committed page. |
| pagination_order_or_range / pagination_boundary_inconsistent | API result violates expected ordering/boundary behavior. Retry, then investigate; the cursor does not advance over the uncertain page. |
| existing_bank_provenance_requires_recovery | Source history and standard bank rows disagree, often after a partial restore/reinstall. Restore a consistent backup or have a maintainer inspect the records. |
| internal_error_* | A framework/database/customization error occurred. Reproduce on sanitized staging data. Production logs intentionally omit payloads and secrets. |

## Review procedure

1. Open the source record, its Source History and Source Legs. Compare it with the official bank statement. Resolve configuration/fee issues first while the connection is disabled.
2. If an already imported amount/date/state changed, review linked ERPNext vouchers. Remove Bank Transaction reconciliation links through normal ERPNext accounting operations. The connector does not undo GL postings or make decisions about those vouchers.
3. A System Manager opens the source record and chooses Review and Apply, records a meaningful note, and applies the current bank evidence. The action fetches the transaction again; it cannot use a stale webhook snapshot.
4. Conflicting, unlinked rows are cancelled; replacements are created only when the latest completed movement requires them. Unchanged rows are retained. Reconcile the current submitted rows as appropriate.

A failed apply is atomic for that transaction: no subset of its legs is applied. Old bank rows and previous source snapshots remain available. Sources may retain sensitive descriptions and references, so avoid copying them into public issue reports.

## Backfill and restoration

Use Historical Backfill for missed creation-date ranges and after adding/re-enabling mappings. To import older history, first move Historical From earlier, then request backfill. Merely editing Historical From does not rewind the poll cursor. Through dates are inclusive UTC dates, unlike the API's exclusive `to` timestamp.

Do not edit hidden page cursors directly. Each active window stores its fixed start/end and next descending `to`. A failed page replays, and later pages cannot be mistaken for a completed window. API grants are refreshed outside transaction-import savepoints and committed immediately because refresh invalidates the old token remotely.

Back up database, site files and the matching encryption key together. Restoring the DB without the key makes encrypted secrets unreadable. Restoring bank rows without source/leg history can result in a deliberate provenance conflict. Never delete source keys to make an error disappear. Compare imported periods and totals after any restoration.

## Capacity and known boundaries

- Source history starts at Historical From. Changes to earlier transactions are only known if a webhook supplies their ID or you explicitly extend history and backfill.
- Old completed transaction changes can take one full rotating-audit cycle to discover without webhooks. Audit cadence depends on historical span and window size.
- Each pending batch handles at most 50 records; every connection job has bounded runtime. Monitor backlog and dedicate long workers for busy connections.
- One connection belongs to one Company. Cross-company transfers appear in each Company's separate feed and require proper intercompany accounting by your accountant.
- Idempotency covers this app's source keys. It cannot identify an equivalent untagged CSV/Plaid import reliably. Choose a clean cutover period.
- PostgreSQL is not a supported deployment target. Validate live Revolut imports against your own statements.

## Uninstall and reinstall

Disable all connections, drain all jobs and resolve every source review before uninstall. Export source/revision/leg/log records first. Externally delete the webhook registration and revoke the certificate/consent; clearing local fields does not revoke access at Revolut. Uninstall is a deliberate destructive operation on the app's configuration/history.

```bash
bench --site SITE backup --with-files
bench --site SITE uninstall-app revolut_bank_feed
```

Standard ERPNext Bank Transactions remain, including cancelled history. The app's custom provenance/review/fee fields are deliberately retained and contain no Links to deleted app DocTypes. Once the app is uninstalled its reconciliation guards no longer execute, which is why reviews must be resolved first. Preserve the fields unless a reviewed migration replaces them.

Frappe's uninstall removes app DocTypes/configuration. Treat the backup as containing valid secrets until you revoke them externally. On reinstall, restore the matching source history before importing overlapping periods, or choose a clean cutover after careful comparison. Do not use uninstall/reinstall to reset watermarks. Removing the app from the bench/image is a separate step after it is uninstalled from every site using it.
