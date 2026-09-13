# Browser setup revision

The /app/revolut-setup Desk page is a four-step setup flow plus an overview. It uses existing Frappe controls, theme variables, accessible labels and keyboard focus. A narrow blue progress indicator describes actual setup progress; accounting data stays in a plain currency/account table. No marketing hero, external fonts or third-party assets.

1. Select Company, Sandbox/Production and history start. A resumable disabled connection is created.
2. Generate the RSA key and X.509 certificate on the server. Only the public certificate reaches the browser. Show exact Revolut registration instructions and redirect URI; collect Client ID.
3. Open READ consent in Revolut. Paste the redirected URL or short-lived code into a Password-style control and exchange it. No shell commands.
4. Discover accounts. Select existing Bank Accounts using currency-matched choices; optionally create a Bank Account against an existing bank ledger. Validate all selections server-side, then enable and queue the first sync.

The overview provides connection selection, status, Sync Now, pause/resume, historical backfill, reviews and advanced settings. Durable state is read from the server after reload; no tokens/private keys in localStorage. A public minimal authorization landing page has no third-party content, scripts or logging of credentials by this app; the operator must suppress query strings at the proxy. The user explicitly pastes the code rather than relying on undocumented OAuth state support.

Installation remains a hosting operation: private Frappe Cloud bench-group dashboard or the documented Bench/custom Docker image. The connector cannot install itself before its Python code exists on the server. No server-command executor or zip-upload installer is exposed in Desk.
