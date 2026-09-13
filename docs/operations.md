# Troubleshooting

[All guides](README.md)

Start in **Connect Revolut → Sync logs**. Check the latest status and error code, then use the matching fix below.

## Common problems

| Problem | What to do |
| --- | --- |
| Cannot find the app | Sign in as a **System Manager**. Look for **Home → Revolut Bank Feed** or search **Connect Revolut**. After an update, run migration and hard-refresh the browser. |
| No Business API option in Revolut | Check that you have **Grow or above** and permission to manage APIs. |
| Accounts appear but no transactions | Finish authorization, map the accounts, activate the feed and click **Sync now**. Account discovery alone does not import transactions. |
| Authorization expired or failed | Start authorization again and paste the new returned URL within two minutes. Check the Client ID and exact redirect address. |
| Certificate already configured | Continue with the saved certificate. Do not create a second connection. If setup offers to repair a missing private key, follow that flow and register the replacement certificate in Revolut. |
| Sync is queued but never starts | Ask your administrator to check the scheduler and worker consuming the **long** queue. |
| Sync is catching up | Let it continue. Older history is processed in batches; check the **Poll Cursor** on Revolut Connection. |
| Transactions need review | Follow the review steps below. |
| Expenses or receipts are unavailable | Use Production and check access to the feature in Revolut. Disable unavailable optional data; the bank feed can continue. |
| No FX quotes | Follow the checks in [Exchange rates](exchange-rates.md). |
| Sidebar disappears on `/banking` | Expected: this is ERPNext’s separate Banking app. Use its **Home** link to return to Desk. |

## Transactions need review

1. Open **Connect Revolut → Review transactions**.
2. Compare the source record with your Revolut statement.
3. For fee or mapping issues, pause the connection and correct the setup first.
4. If an imported transaction changed, have your accountant review its vouchers and remove reconciliation links before applying the change.
5. As a System Manager, use **Review and Apply** on the source record and enter a useful note.
6. Reconcile the resulting Bank Transactions as needed.

The app retains previous evidence. It does not undo accounting vouchers for you.

## Import missing or older transactions

1. Open **Connect Revolut → Import older transactions**.
2. Choose the date range and submit it.
3. Check progress in **Sync logs**.

- Use this after adding or re-enabling an account mapping too.
- If the requested start is earlier than **Historical From**, move that setting earlier first.
- Changing Historical From alone does not restart the import.
- Avoid overlapping a previous CSV or other bank-feed import; this app cannot reliably identify those duplicates.

## Common error codes

| Code | Next step |
| --- | --- |
| `connection_busy` | Wait for the current job, then retry. |
| `authorization_required` / `missing_refresh_token` | Reauthorize the existing connection. |
| `revolut_http_401` / `revolut_http_403` | Check API access, consent and any Revolut IP allowlist. |
| `revolut_http_429` | Let the scheduler retry after the rate limit clears. |
| `revolut_network_error` / `revolut_http_5xx` | Retry later; saved progress is retained. |
| `no_account_mappings` | Map at least one account before importing. |
| `fee_policy_review_required` | Compare the statement and set the account mapping’s fee policy. |
| `currency_exchange_already_exists_not_overwritten` | Review the existing ERPNext rate; it has been preserved. |

[Full diagnostic-code reference](operations-reference.md#common-diagnostic-codes)

## Updates and backups

- Pause the feed and let active jobs finish.
- Back up the **database, site files and matching encryption key** together.
- Deploy the updated image to all Frappe services, run migration and restart workers.
- Re-enable the feed and check the first sync. [Deployment steps](../docker/INTEGRATE-EXISTING-DEPLOYMENT.md).
- Do not uninstall/reinstall or delete source history to reset a failed sync.

## Reporting a problem

Include the app version, ERPNext version, error code, and what you were doing. Remove account details from screenshots. Never include private keys, tokens or authorization URLs.

[Report an issue](https://github.com/GreatWharf/erpnext_revolut/issues) · [Administrator reference](operations-reference.md)
