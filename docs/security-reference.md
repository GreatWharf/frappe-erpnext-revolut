# Security model

## Trust and permissions

System Managers configure connections/maps and execute setup/sync/review actions. Those actions also check document permissions, including Company User Permissions where configured. Connector source records, revisions, events and logs are restricted to System Managers; accounting users work with standard Bank Transactions under ERPNext's permissions. A System Manager is a trusted site administrator, not a tenant-security boundary. For mutually untrusted businesses, use separate Frappe sites.

Background jobs run as Administrator against the configured connection and Company. They do not accept untrusted Company, Bank Account or API-host overrides. Maps are validated before active imports, and paused mappings retain their source identities. Browser-supplied authentication/sync cursors are rejected by Connection validation. Internal state is written by server functions.

The read-only guarantee applies to Revolut API operations. The app necessarily creates/cancels local ERPNext Bank Transactions for the bank feed, but never posts accounting vouchers or calls Revolut money-movement/write endpoints.

## Credentials

The private key, access token, refresh token and webhook secrets use Frappe Password fields and the framework's encrypted `__Auth` storage. Private PEM bytes are base64-encoded only to fit single-field transport, then encrypted at rest by Frappe. Base64 is not encryption. The site `encryption_key` must be backed up securely and retained during container replacement.

Only token acquisition uses POST, to a fixed environment-specific auth endpoint. HTTP redirects are disabled so credentials cannot be forwarded to a changed host. Signed assertions last five minutes. Token refresh and API use are serialized per connection because refresh invalidates the prior access token. A READ-only consent URL is provided; responses that explicitly report broader scopes are rejected. If scope is omitted, correctness of the original consent remains an operator responsibility.

The application does not record token request bodies, response bodies or arbitrary exception tracebacks. Client exceptions use safe codes. Do not enable HTTP debug logging, request-body tracing, Frappe Recorder or third-party APM capture on credential endpoints in production. Site backups and reverse proxies need their own access controls; encrypted database fields do not protect a compromised running application server.

## Webhook security

The public method `revolut_bank_feed.webhooks.receive` supports POST only. A random key locates a connection, but HMAC authenticates the payload. The handler validates the exact received bytes, timestamp tolerance and signature before saving a minimal event ID. It accepts current/previous secrets to support rotation. It never imports the incoming JSON as bank evidence: the worker retrieves the authoritative transaction by ID through the READ API.

Duplicate payloads share a durable inbox key. Repeated but differently encoded legitimate events can create multiple inbox records; the source ledger and unique bank keys still make processing idempotent. Delivery order does not matter because each event causes a fresh GET. Completed webhook records are retained for 30 days; source identities are retained indefinitely.

Keep HTTPS enabled, allow required Revolut headers through the proxy, enforce body limits (the handler accepts up to 256 KB), and rate-limit this path using your reverse proxy. Frappe may parse the body before reaching the method, so enforce the size limit at the proxy as well. Never turn off site-wide CSRF protection. Revolut should not send ERPNext session cookies. Use accurate NTP-synchronized time; old/future signatures outside five minutes are rejected.

Keep query strings off authorization redirect and webhook access logs where feasible. Do not use a redirect page with analytics, external scripts or third-party links that can leak short-lived codes. Do not send codes, keys or tokens in support requests.

## Lifecycle

Rotate certificates before expiry, using the same connection to preserve identity. Disable/save the connection, wait for its job to finish, update the key/client/issuer as needed, perform READ consent, then re-enable. Webhook registration and signing-secret rotation are external provisioning operations requiring separate authorization; the connector has no WRITE scope.

Before removing the app, revoke the credential/consent and webhook in Revolut and protect or destroy exported secrets according to your organization's policy. Uninstalling local code does not revoke a remote token. Report security issues privately to the maintainer of your deployed repository; no fabricated support address is provided in this distribution.

## Additional evidence (0.3)

Account snapshots, expenses, quotes and accounting reference records are restricted to System Managers, with Company links and ordinary document permission checks on Desk actions. They do not expose credentials. Expense payer/merchant information and receipts are sensitive accounting evidence; apply your retention and backup policies. Receipt attachments are private and attached to the restricted expense document, not publicly linked. Only PDF/PNG/JPEG signatures are accepted, with an 8 MiB streaming cap. This is format checking, not malware scanning; retain your organization's normal attachment scanning controls.

Currency Exchange creation requires the user's normal permission and an explicit button action. The target DocType is site-wide rather than Company-specific. Existing rates are never overwritten. Expense invoice/claim links check the target Company and read permission. No automatic Supplier, employee reimbursement or tax configuration is created. Extra-data sync failures have separate status and do not stop the bank job.
