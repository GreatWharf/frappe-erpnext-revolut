# Design and compatibility contract

This is a Frappe/ERPNext v15 app, targeting Python 3.10+ and MariaDB. It does not create accounting vouchers or post to the General Ledger. Each Revolut Connection belongs to one ERPNext Company; multiple connections provide multi-company support and separate credential boundaries. Each account/currency maps once per environment and once per ERPNext Bank Account.

## Components

- `core.py`: pure Decimal normalization, identity, mapping checks, import decisions, defensive time pagination.
- `client.py`: allowlisted GET endpoints, token exchange/refresh with fresh RS256 assertions, timeouts and bounded retries. Only OAuth token POST is supported.
- `auth.py`: encrypted token/key persistence, connection-wide lock and authorization URL with READ scope.
- `sync.py`: queued sync, per-transaction commits, bounded historical windows, overlap polling, pending rechecks, rotating historical audit, persistent webhook inbox processing.
- `importer.py`: source records and submitted standard Bank Transactions. Unique source keys survive credential replacement. Financial changes on existing submitted records require review; explicit review action cancels/replaces only after reconciliation links are removed. Original documents and source revisions remain auditable.
- `api.py`, `webhooks.py`, Desk controllers: role-gated actions, signed webhook ingestion and reconciliation safety guard.

## Durable data

Connection stores encrypted base64 PEM private key, access/refresh tokens and webhook secret. Account Map pins company, account, currency, timezone and fee policy. Source Transaction stores a reduced JSON snapshot (no cardholder/phone/raw card data), upstream state/version and review reason. Source Leg stores stable identity and the active Bank Transaction link. Sync Log stores safe diagnostic codes and counts. Webhook Event stores only connection, event identity and transaction ID.

## Hard cases

Only completed transactions produce bank statement rows. Created/pending remain in the source ledger and are revisited. Unsuccessful/reverted records do not fabricate opposite-sign movements; existing rows are blocked from further reconciliation until reviewed. Refunds and chargebacks with their own IDs import normally. FX legs retain their own currency and original billing metadata; mismatched account currency is held for review. Fee-bearing legs default to Review because public field descriptions do not unambiguously guarantee net/gross semantics. An operator selects Amount includes fee or Deduct fee from amount after comparison with statements; both preserve reported fees and avoid automatic GL entries.

Pagination follows created_at descending and exclusive to. Full-page boundary timestamps are probed with a one-microsecond window before advancing; >=1000 transactions at one timestamp is explicitly an error, since the API supplies no tie cursor. Poll watermarks advance only after a complete window succeeds. Durable transactions can safely replay after failure.

## Security and deployment

Only System Manager can configure connections or run privileged actions. Company links support Frappe User Permissions; source data and logs are restricted to administrators. Standard Bank Transaction permissions remain ERPNext-owned. Webhook body is verified byte-for-byte with HMAC SHA256 and a five-minute timestamp tolerance before durable ingestion. No global CSRF bypass. Webhook registration needs an external WRITE-authorized setup operation and is deliberately absent from the connector. Polling needs only READ.

A complete live bench is not available in the authoring environment. Pure/mock tests and package checks are run locally; bench integration tests and a deployment acceptance checklist ship with the repository. No claim of live-bank or Docker validation is made without running it.
