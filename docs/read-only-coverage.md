# Data coverage

[All guides](README.md)

## What you get

| Data | Where it appears | Schedule |
| --- | --- | --- |
| Completed transactions, refunds and FX account movements | **Bank Transaction** | Every 15 minutes |
| Account balances, including unmapped accounts | **Revolut Account Snapshot** | Hourly |
| Current exchange-rate quotes | **Revolut FX Quote** | Daily, when enabled |
| Expenses and their details | **Revolut Expense** | Hourly, when enabled |
| Receipt attachments | Private files on **Revolut Expense** | With expense sync, when enabled |
| Categories, tax rates and labels | **Revolut Reference** | Daily, when enabled |

## Enable optional data

1. Open your active connection in **Connect Revolut**.
2. Click **Choose extra data** and select what you need.
3. Click **Refresh extra data** to queue a run.
4. Open **FX quotes**, **Expenses and receipts**, or **Categories and taxes** to see results.

- Optional features start off. Account balances are included automatically for enabled connections.
- Expenses and receipts need **Production** and access to those Revolut features.
- Manual refresh still respects the daily FX and reference-list limits.
- Extra-data errors are reported separately from bank-feed errors.

## How this fits into ERPNext

- **Bank feed:** creates Bank Transactions for you to reconcile. It does not create accounting vouchers.
- **Fees:** some transactions need review before import. Compare them with the statement before choosing a fee policy.
- **Balances:** snapshots for reference; they do not change your general ledger.
- **Exchange rates:** review a quote before saving it to ERPNext. [How to use rates](exchange-rates.md).
- **Expenses:** link to an existing Purchase Invoice or Expense Claim after review. No automatic bills or reimbursements. Expense Claims require HRMS.
- **Receipts:** private PDF, PNG or JPEG files, up to 8 MiB each. Unsupported files remain pending.

## Not included

- Sending payments or exchanging money.
- Issuing cards, viewing card security details or managing spending programs.
- Automatically creating Suppliers, bills, claims or tax rules.
- Historical market exchange rates.

The app requests **READ access** to Revolut. You remain in control of reconciliation and accounting in ERPNext.

[Sync schedules and limits](sync-reference.md) · [Troubleshooting](operations.md)
