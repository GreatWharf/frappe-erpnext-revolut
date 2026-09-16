# Troubleshooting Revolut Bank Feed

[Back to Revolut Bank Feed help](README.md)

Start in **Connect Revolut → Sync logs**. The latest message usually tells you what needs attention.

## Common problems

| What you see | What to try |
| --- | --- |
| I cannot find the app | Sign in as a **System Manager**, then search for **Connect Revolut** or open **Revolut Bank Feed** from the ERPNext home screen. |
| Revolut has no Business API option | Check that the account is on **Grow or above** and that you can manage API settings. |
| I can see accounts but no transactions | Finish the connection, match at least one account, activate the feed, and choose **Sync now**. |
| Setup says the certificate is already configured | Continue with the saved connection. Do not create a second connection just to restart setup. |
| Authorization failed or expired | Start the approval step again and paste the new returned page address within two minutes. |
| Sync is still catching up | Leave it running. Older history is imported in batches; check the sync log for progress. |
| Expenses or receipts are missing | Use a Production connection and check that your Revolut account includes those features. |
| The `/banking` sidebar disappeared | This is ERPNext's separate Banking page. Use its **Home** link to return to Desk. |
| No FX quote appears | Turn on **Daily FX quotes**, make sure you have accounts in more than one currency, and refresh extra data. |

## When a transaction needs review

1. Open **Connect Revolut → Review transactions**.
2. Compare the item with the Revolut transaction or statement.
3. Fix the account match or fee choice while the feed is paused.
4. Choose **Review and Apply** and add a short note.
5. Reconcile the resulting Bank Transaction in ERPNext.

The app keeps the original evidence. It does not undo accounting work automatically.

## Import older history

1. Open **Connect Revolut → Import older transactions**.
2. Choose the date range and submit it.
3. Watch **Sync logs** until the import finishes.

Use this after adding a new account match as well. Avoid importing the same period through another bank-feed tool at the same time.

## If automatic syncing stops

Ask your ERPNext administrator to check that the site's scheduler and background workers are running. A manual **Sync now** still needs the same background services.

## Reporting a problem

Include the app version, ERPNext version, the visible error message, and what you were doing. Remove account details from screenshots. Never share private keys, tokens, or authorization URLs.

[Detailed administrator reference](operations-reference.md)
