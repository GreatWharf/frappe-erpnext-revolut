# Deployment acceptance checks

Run these against a disposable v16 staging site and Sandbox first. Record Frappe/ERPNext versions, app revision, Docker image digest, test output and comparison results. Do not use a production site's accounting data for automated fixture tests.

## Installation and permissions

- Install ERPNext then the app on a fresh MariaDB site; migrate twice and verify custom fields/indexes remain valid.
- Run the supplied bench integration test module. Confirm ordinary users/Accounts Users cannot read connector secrets, discover accounts, start arbitrary connections or invoke review actions.
- Configure Company User Permissions for a restricted System Manager and verify per-document access on the intended deployment.
- Check the custom image on every Frappe service, restart all services, and confirm app/secret persistence.

## Authentication

- Use a Sandbox certificate and the generated READ consent URL. Exchange a fresh code; reject an expired code.
- Confirm private key/tokens are masked in Desk and encrypted in storage. Check application/APM/proxy logs for absence of credentials.
- Exercise access expiry, one 401 refresh, revocation and reconnection. Run Sync Now twice concurrently and verify serialization/idempotency.
- Verify the saved issuer and production/sandbox host selection against the registered certificate.

## Accounting and recovery

- Compare completed deposits and withdrawals against a statement. Confirm Bank Transactions are submitted and unallocated, and no GL Entry/Payment Entry/Journal Entry was created by the feed.
- Test pending → completed and pending → reverted. Verify pending items are not available to reconcile.
- Test a two-leg FX movement, a fee-bearing outgoing/incoming movement, a separate fee and a refund with a related transaction. Choose fee policy only after reconciliation to actual balances. Confirm no currency substitution from bill_amount.
- Re-fetch identical transactions and overlapping backfills; assert one active Bank Transaction per source leg. Verify a page with equal created_at timestamps imports all IDs.
- Interrupt a job after a committed page, restart it, and confirm checkpoint recovery. Simulate 429/5xx and verify the saved cursor never skips an uncertain page.
- Simulate a financial/state change after import and after partial/full reconciliation. Verify the review flag blocks new allocations, allows removing links, and refuses Review and Apply until links are removed. Confirm a correction preserves cancelled originals and creates only the appropriate replacement.
- Pause a map, retire its bank ledger, and verify other maps still sync and old rows remain. Re-enable and backfill to recover changes during the paused period.
- Exercise two Companies with separate connections/currencies. Verify wrong-company/wrong-currency mapping is rejected and duplicate mapping is rejected at the DB level.

## Webhooks and scheduling

- Provision webhooks externally if used. Deliver both supported events to the exact public URL.
- Reject altered bytes, wrong secret, missing signature and out-of-tolerance timestamps. Test secret rotation, duplicate and out-of-order delivery.
- Stop workers, deliver a valid event, restart workers and confirm durable recovery. Confirm a failed event does not stop periodic polling.
- Verify a scheduler run occurs without manual clicks. Verify pending rechecks and the daily rotating audit detect old changes.
- Monitor application-level Error/Review Required and stale Last Success, not merely RQ success.

## Upgrade and recovery

- Take a staging backup with the site's encryption key, restore it to a separate site, and confirm credentials/source/bank rows remain consistent.
- Build/deploy a new app image, migrate and run a small overlap sync without duplicates.
- Exercise uninstall on a disposable copy only: disable/drain, resolve reviews, export audit records, uninstall; confirm standard Bank Transactions and provenance fields remain.

Promote to Production only after these checks pass in your environment and a representative statement period balances. This checklist describes work still required at deployment; it is not evidence that a live deployment was tested during code generation.

## Additional data (0.3)

- Upgrade a staging copy from 0.2; confirm existing connections receive a 60-minute overlap without changing identities or generating replacement Bank Transactions.
- Confirm the hourly extra-data schedule and long worker, and verify optional feature failures leave the bank job operational.
- Check all own account currencies/balances, including unmapped accounts; compare timestamps with a bank statement rather than assuming GL equality.
- Verify one quote direction and fee against Revolut; ensure Currency Exchange creation refuses a pre-existing pair/date and requires normal accounting permissions.
- With an appropriately controlled Production connection, import expenses (Sandbox unavailable), compare splits, VAT, labels and linked transaction IDs, then repeat sync to check deduplication.
- Confirm a private receipt is unavailable to a guest or an unauthorized user, survives an image update and is not downloaded twice. Test a failed/unsupported receipt while newer expenses continue importing.
- Link an invoice/claim from the same Company, reject a different Company, and check a changed upstream expense flags local review without changing the accounting document.
- Confirm old receipt additions/expense changes are recovered through rotating audits and manual refresh. Review catalogue last-seen timestamps before using archived definitions.
