# Data model and accounting rules

## Records

| Record | Purpose |
| --- | --- |
| Revolut Connection | One Company/environment/credential boundary, scheduler cursors and encrypted secrets |
| Revolut Account Map | Immutable account/currency/Bank Account/timezone binding; fee policy and pause switch |
| Revolut Source Transaction | Latest reduced upstream evidence, upstream state/time, review status |
| Revolut Source Revision | Previous evidence when a source payload changes |
| Revolut Source Leg | Stable leg identity, revision and current Bank Transaction link |
| Revolut Webhook Event | Durable, deduplicated delivery inbox containing only transaction ID/event metadata |
| Revolut Sync Log | Safe diagnostic codes, attempted/created/review counts and outcome |
| Bank Transaction | Standard submitted ERPNext statement row, plus four provenance/review/fee fields |

The app omits card numbers, cardholder name, phone and authorization codes from the source snapshot. It retains transaction IDs, timestamps, state, reason, relationship, reference and reconciliation-relevant leg fields, including bill currency/amount and optional running balance. Descriptions and references may still contain personal/business information. Restrict and back up these records accordingly.

## Monetary representation

API JSON floating-point amounts are parsed as Decimal. Signed account-leg amount is converted to either deposit or withdrawal, with the other zero. The completed timestamp determines the statement date in the mapping's timezone; creation time controls retrieval only. Amounts use the leg's currency. Billing amounts are evidence about an underlying purchase/FX operation and never replace the mapped account currency or cause a guessed exchange rate.

Unknown account/currency, missing IDs, unsupported state, negative/invalid fee or an ambiguous fee policy produce a review/error instead of a guessed import. A currency mismatch is not automatically converted. If ERPNext changes an amount through configured precision during insertion, the transaction unit rolls back with `bank_amount_precision_or_schema_mismatch`; configure an appropriate currency precision and replay.

### Fee policy

For signed amount `A` and nonnegative reported fee `F`:

| Policy | Imported signed amount |
| --- | --- |
| Review | Import only if F is zero; otherwise retain source for review |
| Amount includes fee | A |
| Deduct fee from amount | A − F |

Examples: `A=-10, F=0.15` becomes a withdrawal of 10.15 under Deduct; `A=10, F=0.15` becomes a deposit of 9.85. A zero amount plus a nonzero deductible fee becomes a fee-only withdrawal. A zero net result creates no statement row. Standalone transactions of type fee/charge import by their own leg amount. Do not choose Deduct if your statements already reflect the fee in the leg amount or report the same charge separately. Validate transfer, card and exchange examples for your account; if semantics vary by transaction type, keep Review and extend the policy with verified fixtures before enabling automatic fee imports.

The app retains `custom_revolut_fee`; it does not set ERPNext's excluded_fee and risk its save hooks adding the fee twice. No fee expense is posted automatically.

## State changes

| Upstream state/event | Action |
| --- | --- |
| created / pending | Retain source, recheck periodically; no Bank Transaction yet |
| completed, first observation | Import each enabled mapped nonzero leg |
| Same completed transaction again | No duplicate; provenance and monetary values checked |
| Completed amount/date/currency/account changes | Flag review; preserve existing submitted rows |
| reverted / failed / declined before import | Observe only |
| reverted / failed / declined after import | Flag review; no synthetic refund |
| Explicit Review and Apply | Re-fetch current transaction; refuse if conflicting rows have reconciliation links; cancel/recreate as warranted |
| Separate completed refund/chargeback | Import its own ID and signs; retain related_transaction_id if supplied |
| Older updated_at than saved evidence | Ignore older payload |

A review applies to the transaction as a whole. Unknown legs hold the entire transaction, so an incomplete FX transfer is not silently presented as complete. Once all required mappings exist, use Review and Apply or replay that creation-date range. Fees or mapping issues can resolve automatically on replay if they have not changed an existing bank row. Financial changes to existing rows always require explicit review.

Pausing a map preserves its historical rows and does not cancel them. Its old rows are excluded from current source-update processing while paused; if a review was already outstanding, it remains outstanding until the map is re-enabled and reviewed. Paused periods need backfill when resumed.

## Identity, recovery and retention

A source row name hashes connection + transaction ID. A source leg name hashes environment + account ID + currency + transaction ID + leg ID. A bank-entry key additionally hashes the local revision. The latter is unique in the database. Revising authentication on the same connection does not change leg identity. Separate environments cannot collide.

Every API transaction's source updates and all of its new bank rows commit together. A failed transaction cannot leave half of an FX import committed. Earlier successful transactions in a window remain durable, and failed windows safely replay. Cursors for polling, backfill and audit are independent; active windows freeze their upper bound and checkpoint after complete pages.

Revolut's exclusive `to` timestamp can omit ties at a full-page boundary. The app probes the boundary with a one-microsecond interval before continuing. If 1,000 or more transactions share that exact timestamp, there is no documented secondary cursor: the app stops with `pagination_tie_saturated` and retains its checkpoint for explicit investigation.

Source/leg/revision history is never automatically purged. Done webhook entries retain 30 days; finished sync logs retain 90 days. Records restored without matching bank/source tables are not silently adopted. An existing bank provenance key without its matching ledger record produces `existing_bank_provenance_requires_recovery`.
