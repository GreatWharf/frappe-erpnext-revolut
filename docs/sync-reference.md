# Sync reference

## Enable from the frontend

After deploying the new image and migrating the site, open **Connect Revolut → Choose extra data**. Select FX quotes, expenses, private receipts and accounting reference lists as needed. These options start off so existing sites can enable the features their Revolut account supports. **Accounts and balances** are imported automatically for enabled connections. Use **Refresh extra data** to queue a run; FX and catalogue daily limits still apply. The main bank feed and extra-data jobs have separate status and error reporting.

Only GET endpoints retrieve business data. OAuth code exchange and refresh still use POST `/auth/token`; authentication necessarily sends a signed assertion and authorization grant. There are no payment, exchange, reimbursement, expense-update, webhook-registration or other business-data write calls to Revolut. READ remains the only consent scope.

## Coverage

| Revolut information | ERPNext destination | Behavior |
| --- | --- | --- |
| Completed bank activity, fees, refunds, reversals and both FX account legs | Standard Bank Transaction plus source history | Existing mapping, uniqueness and reconciliation safeguards remain |
| Original bill amount/currency | Bank Transaction custom fields | Includes effective bill-currency units per account-currency unit, computed from reported amounts; fee remains separate |
| All own accounts, currencies, state and balance | Revolut Account Snapshot | Hourly, including unmapped accounts; links mapped Bank Accounts; never changes GL balances |
| Current sell FX quotes, quote timestamp and fee | Revolut FX Quote | Daily, each active account currency → Company base currency, amount=1 |
| Explicit adoption of today's quote | Standard Currency Exchange | Button requires normal create permission, refuses existing pair/date, never overwrites another provider's rate |
| Expense status, merchant, payer, description and source transaction | Revolut Expense | Incremental hourly import; auto-links matching source transaction when available |
| Expense splits, categories, tax names/percentages and labels | Expense details and stored evidence | Readable split table; original tax/label evidence retained |
| Receipt IDs and supported files | Private File attachments on Revolut Expense | PDF/PNG/JPEG, maximum 8 MiB each, batched retries; no public attachments |
| Invoice/claim association | Link to existing Purchase Invoice or Expense Claim | Explicit choice, same Company, permission checked; never submits or creates reimbursement |
| Accounting categories, tax-rate definitions, label groups and labels | Revolut Reference | Daily paginated mirror for review/mapping; never rewrites ERPNext's Chart of Accounts or tax templates |

The FX endpoint returns a current indicative sell quote, not historical market rates. The effective bill rate is a ratio of the reported bill and account amounts, not a guaranteed fee-inclusive execution rate. For FX exchanges without original bill fields, the source retains the two account legs; no historical market rate is invented.

Currency Exchange in ERPNext v16 has **no Company field**. Adopting a quote is therefore an explicit site-wide action. An existing rate is retained; a previously adopted quote is not silently refreshed. Buying/selling flags refer to ERPNext document use, not Revolut currency-buy/sell execution. A quote is for one unit and may differ from a larger transaction's actual price or fee.

Expenses are evidence of spending, not automatically employee debts. A company-card purchase is already paid; generating an Expense Claim for every card purchase could duplicate liabilities. Review and create any accounting document through the normal ERPNext workflow, then link it. Expense Claim is available only when the appropriate HRMS app is installed on v16. No HRMS dependency is added to this app. If linked expense evidence changes, the expense is flagged for accounting review; the invoice/claim is left untouched. Re-link after reviewing to acknowledge the change.

## Precisely what each sync reads

- **Every 15 minutes:** transactions from the saved cursor minus **60 minutes** through the next bounded interval; up to 50 pending IDs and 50 queued webhook events. Once caught up, this is the new interval plus a one-hour overlap. Set Routine overlap (minutes) between 1 and 1440 if needed.
- **Once daily:** recheck the most recent **7 days** (Lookback Days), and independently audit a rotating **30-day** historical slice. Existing configured lookback/audit values are retained. Audits are necessary because a purely new-ID feed misses old reversals.
- **Backfill:** bounded **7-day** transaction windows with durable page checkpoints. It progresses from the requested start and does not restart at the beginning every run.
- **Hourly at minute 7:** one all-accounts call, incremental expenses if enabled, then optional receipt work. Jobs share a connection lock and never run simultaneously against the same connection. A busy run is skipped and retried by the next schedule.
- **Expenses:** seven-day catch-up windows, one-hour overlap once caught up, and a rotating 30-day audit once a day. Up to 20 old unfinished expenses are individually revisited per run. Approval/receipt edits to older completed expenses appear during their historical audit or immediately through Refresh expense and receipts.
- **Receipts:** up to 20 pending expense records per run, at most 100 receipt IDs per expense. Saved receipt IDs are not downloaded again unless the file is missing. A failed/unsupported receipt remains pending with a diagnostic code; it does not stop expense discovery or the bank feed. If upstream replaces content under the same receipt ID, it is not detected automatically: remove the local attachment and refresh that expense to re-download after retaining any required audit copy.
- **FX/catalogues:** daily. FX requests are linear in account currencies, not every possible currency pair. Catalogues have opaque cursor pagination; they are small reference lists rather than transaction history. Missing catalogue records remain historical evidence with their last-seen timestamp; absence is not inferred as permission to delete local accounting configuration.

Both transaction and expense pagination handle timestamp ties before advancing a cursor. If a single timestamp saturates the API limit, import stops with an explicit error rather than silently skipping data. Expenses use their `expense_date` (not an invented updated-since filter), at most 500 per tie request. Progress survives worker interruption; replayed pages upsert by stable identity. Retrying a page may revisit records but does not create duplicates.

These bounds reduce scanning but cannot eliminate every repeat read: pending states, delayed bookings and amended expenses require checks. Bank logs report transactions seen, new bank rows and reviews. Extra logs identify failing features; `Extra Success` indicates an extra-data run, not a bank reconciliation run. Balance observations are not continuously streamed and are not a ledger reconciliation assertion.

## Deliberate limits

The connector does not mirror everything merely because it has a GET endpoint. Card credentials, card security details, payment drafts, team administration, counterparties as automatically created Suppliers, and operational API-management records have no reliable automatic ERPNext accounting mapping here. No READ_SENSITIVE_CARD_DATA scope is requested. Revolut merchant names are not assumed to identify a particular Supplier or tax registration. Receipts in unsupported formats stay visible as pending evidence rather than being executed or exposed publicly.

Expense/receipt APIs are **Production only**, according to Revolut's current documentation. Availability also depends on your account's features. A 403 or unsupported feature is reported separately; disable that option if unavailable. No live Production expense calls were made during development.

## Upgrade and verification

Keep the existing connection and source history. Pause connections, back up, deploy the new app image to all Frappe services, run site migration and restart workers/scheduler as described in the Docker guide. Migration adds four evidence DocTypes, read-only status fields, bill-rate Bank Transaction fields and a 60-minute routine overlap for existing connections. Re-enable connections and select extra features in the frontend. Existing Bank Transaction identities remain unchanged. Bill metadata on older rows is filled as their transactions are revisited.

Validate in staging: check Company isolation, real permissions, receipt private access, FX direction and actual statement samples. Test Expenses in an appropriately controlled Production connection because Sandbox does not expose them. Before uninstalling, export the additional evidence and private receipts too. Custom Bank Transaction fields and explicitly created standard Currency Exchange records remain; app DocTypes are removed by uninstall. Do not uninstall/reinstall to reset sync.

## Official references checked

- [Revolut Business API reference](https://developer.revolut.com/docs/api/business): READ scope, accounts, expenses, receipts, `/rate`, accounting categories/tax rates/label groups and their pagination.
- [Expense and receipt guide](https://developer.revolut.com/docs/guides/manage-accounts/accounts-and-transactions/retrieve-expenses).
- [Revolut exchange-rate guide](https://developer.revolut.com/docs/guides/manage-accounts/exchange-money).
- [ERPNext v16 Currency Exchange schema](https://github.com/frappe/erpnext/blob/version-16/erpnext/setup/doctype/currency_exchange/currency_exchange.json).

Docker deployment, site migration and Desk navigation have been checked on our internal v16 installation. Live Revolut import coverage still needs statement-based validation; local tests use mocked API boundaries.
