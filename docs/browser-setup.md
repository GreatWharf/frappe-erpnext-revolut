# Connect Revolut from ERPNext

Sign in as a **System Manager**, search for **Connect Revolut**, or open `/desk/revolut-setup`. The app must already be installed on the site. An HTTPS site `host_name` must be configured. Creating a Bank or Bank Account also needs the standard ERPNext accounting permissions.

1. **Company.** Choose the ERPNext Company, Sandbox or Production, and the first date to import. Each connection belongs to one Company. Use the connection selector to add further businesses or Companies.
2. **Certificate.** Click **Generate certificate**. The server generates a signing key and stores it in an encrypted Password field. Only the public certificate reaches your browser. Existing private keys are never overwritten by this action.
3. **Connect.** Open Revolut Business API settings and register the public certificate and exact redirect address displayed. Save the Client ID Revolut provides. Click **Open Revolut authorization**, approve READ access, then copy the full returned page address into the setup screen and click **Connect account** within two minutes. The copied address contains a short-lived authorization code: paste it only here. The app clears the input after use. This manual return step avoids relying on an undocumented OAuth state parameter.
4. **Accounts.** Choose an ERPNext Bank Account from each currency-matched dropdown. Leave unwanted accounts blank. If one is missing, use **Create Bank Account** to link an existing bank ledger for this Company. Create any missing bank ledger in ERPNext's normal Chart of Accounts first. Confirm the statement timezone and activate the feed.

The status page provides **Sync now**, refresh, pause, historical backfill and links to transactions, logs and items requiring review. Automatic polling runs every 15 minutes with working scheduler and queue workers. Refresh the page to see updated background-job results. A scheduler indicator checks site settings; it does not prove a worker is healthy—use `bench doctor` during deployment.

Fee-bearing transactions initially require review because API fee semantics can differ. Compare a sample with the Revolut statement and choose the appropriate fee policy in **Advanced settings → Revolut Account Map**. Never guess this setting just to clear a warning. Mapping identities remain fixed once used; use the documented retirement process rather than rebinding old history.

Advanced settings also contain certificate renewal, webhook secrets, audit window controls and source correction tools. Webhooks are optional: periodic polling works without them. Register webhooks using the [README webhook instructions](../README.md#optional-webhooks); the connector itself does not request WRITE permission to create them.

Certificates generated here expire after one year. Revolut refresh-token and consent rules still apply; reauthorize when required. For renewal, pause the existing connection, generate a replacement certificate using the advanced README instructions, register it with Revolut, load its private key using Advanced settings → Authorization → Load Private Key, save the corresponding Client ID and complete READ authorization again. Retain the same connection to preserve import identity. The displayed generated public certificate describes the original key; use your replacement public certificate for renewal. Back up the site's encryption key along with its database. Do not share codes or private keys in support messages.

## Additional data

Use **Choose extra data** on the active connection dashboard to enable expenses, private receipts, FX quotes and accounting reference lists. **Accounts and balances**, **Expenses and receipts**, **FX quotes** and **Categories and taxes** open their respective lists. Read the [coverage guide](read-only-coverage.md) before adopting rates or linking expense accounting documents.
