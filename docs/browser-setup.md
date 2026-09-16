# Connect Revolut to ERPNext

[Back to Revolut Bank Feed help](README.md)

## Before you start

- A Revolut Business **Grow, Scale, or Enterprise** plan.
- ERPNext v16 with the app installed.
- An ERPNext **System Manager** login.
- Permission to manage the Business API in Revolut.
- An ERPNext Company and a Bank Account for each currency you want to use.

## Connect your account

1. Open **Revolut Bank Feed** in ERPNext and choose **Connect Revolut**.
2. Select your Company, choose **Production** for your live account, and choose the date to start importing.
3. Choose **Create certificate**. Copy the public certificate and redirect address shown by ERPNext.
4. In Revolut Business, open **Settings → APIs → Business API** and add those two values.
5. Copy the Client ID from Revolut back into ERPNext and save.
6. Open the Revolut approval page and approve read-only access.
7. Copy the full page address you receive back into ERPNext within two minutes, then finish the connection.
8. Choose the Revolut accounts you want to use and match each one to an ERPNext Bank Account with the same currency. Choose **Skip for now** for accounts you do not recognise.
9. Confirm the timezone, then activate the feed. You can also choose **Save for later** and return when you are ready.

The app keeps the private connection details on your ERPNext site. You only copy the public connection information into Revolut.

## Check the first import

1. Choose **Sync now**, then refresh the status after it finishes.
2. Open **Bank transactions** and compare a few rows with Revolut.
3. Check dates, currencies, amounts, and fees before reconciling.
4. Open **Review transactions** if anything needs attention.

New activity is checked automatically about every **15 minutes** while the feed is active.

## Where to find things

| Task | Where to go |
| --- | --- |
| Reconcile imported rows | **Banking → Banking app** or ERPNext Bank Reconciliation |
| Import older history | **Connect Revolut → Import older transactions** |
| See progress and errors | **Connect Revolut → Sync logs** |
| Turn on expenses, receipts, or FX | **Connect Revolut → Choose extra data** |
| Add or change account matches | **Connect Revolut → Manage accounts** |

If setup stops part-way through, your saved progress is kept. See [Troubleshooting](operations.md) for the usual fixes.
