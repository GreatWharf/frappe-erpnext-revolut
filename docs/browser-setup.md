# Set up the bank feed

[All guides](README.md)

## Before you start

- **Revolut Business Grow, Scale or Enterprise.** [Check API eligibility](https://help.revolut.com/business/help/integrating-with-external-apps/revolut-business-api/question-using-revolut-business-api/).
- App installed on **ERPNext v16**, with an HTTPS site address configured.
- **System Manager** access in ERPNext and permission to manage the Business API in Revolut.
- An ERPNext Company and a bank ledger for each currency you want to import.

## Connect

1. Open **Home → Revolut Bank Feed**. You can also search for **Connect Revolut**.
2. Choose your **Company**, **Production** or **Sandbox**, and import start date.
3. Click **Create certificate**. Copy the public certificate and redirect address shown.
4. Open Revolut Business → **Settings → APIs → Business API**. Register those details.
5. Copy Revolut’s **Client ID** back into ERPNext and save it.
6. Open Revolut authorization and approve **READ access**.
7. Copy the full returned page address into ERPNext within **two minutes**, then finish connecting.
8. Match each wanted Revolut account to an ERPNext **Bank Account** in the same Company and currency. Leave unwanted accounts blank.
9. Confirm the statement timezone and activate the feed.

- No API key goes in Docker. ERPNext stores the private key and tokens encrypted.
- **Create Bank Account** can link an existing bank ledger; create missing ledgers in **Chart of Accounts** first.
- Keep the same connection when reconnecting. Creating a second one is not a way to reset sync.

## Check your first import

1. Click **Sync now**, then **Refresh status** after the background job finishes.
2. Open **Bank transactions** and compare a small sample with your Revolut statement.
3. Check dates, currencies, amounts and fees before reconciling.
4. Open **Review transactions** if any items need attention. [Resolve a review](operations.md#transactions-need-review).

Automatic sync runs every **15 minutes** while the feed, scheduler and workers are enabled.

## Everyday use

| Action | Where to go |
| --- | --- |
| Reconcile transactions | **Banking → Banking app**, or ERPNext’s standard Bank Reconciliation |
| Import older history | **Connect Revolut → Import older transactions** |
| Check progress or errors | **Connect Revolut → Sync logs** |
| Enable exchange rates or expenses | **Connect Revolut → Choose extra data** |
| Add another business | The connection selector in **Connect Revolut** |

The separate `/banking` screen has its own layout without the Desk sidebar. Its **Home** link returns to Desk. Seeing accounts there does not mean transactions have synced.

[Exchange rates](exchange-rates.md) · [Data coverage](read-only-coverage.md) · [Troubleshooting](operations.md)
