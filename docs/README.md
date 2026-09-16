# Revolut Bank Feed help

This guide explains how to connect Revolut Business to ERPNext, check your first import, and resolve the common issues.

## Before you start

- You need a Revolut Business **Grow, Scale, or Enterprise** plan. Basic and personal accounts are not supported. [Check Revolut's current requirements](https://help.revolut.com/business/help/integrating-with-external-apps/revolut-business-api/question-using-revolut-business-api/).
- Your ERPNext and Frappe versions must match: v15 or v16, on MariaDB. See [compatibility requirements](v16-compatibility.md).
- You need an ERPNext **System Manager** account for setup.

## Choose a guide

| You want to… | Read this |
| --- | --- |
| Connect Revolut and start importing | [Set up the bank feed](browser-setup.md) |
| See what the app imports | [Data coverage](read-only-coverage.md) |
| Use Revolut rates in ERPNext | [Exchange rates](exchange-rates.md) |
| Fix a problem or import older history | [Troubleshooting](operations.md) |
| Understand permissions and stored data | [Security](security.md) |

## The normal day-to-day flow

1. Open **Revolut Bank Feed** in ERPNext.
2. Let the scheduled sync bring in new activity, or choose **Sync now**.
3. Review anything flagged for attention.
4. Reconcile the standard ERPNext Bank Transactions.

The feed is read-only. It does not send payments or create accounting vouchers for you.

## A few useful reminders

- Account discovery does not mean transactions have synced yet.
- Optional data such as expenses, receipts, categories, and FX quotes is turned on separately.
- The standalone `/banking` page may use a different layout from Desk. Use its **Home** link to return to ERPNext.
- Keep your normal ERPNext backups, including the site encryption key.
