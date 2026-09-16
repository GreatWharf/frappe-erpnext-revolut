# What the Revolut feed imports

[Back to Revolut Bank Feed help](README.md)

## Included data

| Data | Where you see it | Usual timing |
| --- | --- | --- |
| Completed transactions, refunds, and FX movements | ERPNext Bank Transactions | About every 15 minutes |
| Account balances | Revolut Account Snapshot | Hourly |
| FX quotes | Revolut FX Quote | Daily, when enabled |
| Expenses and receipts | Revolut Expense | Hourly, when enabled |
| Categories, tax rates, and labels | Revolut Reference | Daily, when enabled |

## Optional features

Open **Connect Revolut → Choose extra data** to turn on expenses, receipts, FX quotes, or reference data. Choose **Refresh extra data** to request an update.

Expenses and receipts require a Production connection and the matching Revolut feature on your account. Optional-data errors do not stop the main bank feed.

## What stays in ERPNext

- The bank feed creates standard Bank Transactions for you to review and reconcile.
- It does not create payment entries, journal entries, bills, claims, suppliers, or tax rules automatically.
- Balances are reference snapshots and do not change your general ledger.
- Fees and unusual FX movements may be held for review so the app does not guess.
- Receipt files stay private under the relevant expense record.

## What the app cannot do

The connection is read-only. It cannot send payments, exchange money, issue cards, manage spending programs, or change Revolut account settings.
