# Verification report — 2026-09-12

## Executed locally

Authoring runtime: Python 3.14.7 and Node 24.19.0 on macOS for the v16 port. Test dependencies were installed in an isolated environment. No production credentials or account data were used.

| Check | Result |
| --- | --- |
| pytest unit/mock suite | **109 passed** |
| Ruff lint | Passed |
| Ruff formatting | Passed |
| Python byte compilation | Passed |
| JavaScript syntax checks for all Desk scripts | Passed |
| v16 Page IIFE registration smoke check | Passed |
| Source distribution and universal Python wheel | Built successfully |
| Package/DocType/controller/secret-field structure | Checked |
| Distribution archive contents and CRC | Checked before delivery |

The browser additions test certificate generation and expiry, strict authorization return URL validation, credential exclusion from browser responses, refusal to overwrite existing private keys and activation prerequisites. JavaScript received syntax checks, but the wizard was not executed in a live Frappe browser.

The suite covers Decimal money and equal-value scale changes; Company/currency validation; completed/pending/failed/reverted behavior; independent refunds and same-leg-ID FX; fee policies; unique imports and explicit review; preservation of paused accounts; out-of-order evidence; time pagination and ties; page checkpoint/restart recovery; token refresh with omitted/rotated refresh tokens; READ consent; HTTP endpoint restrictions, 401, rate limits and network retry; HMAC, timestamp tolerance, secret rotation, query-string routing, duplicate delivery and durable queue-failure recovery.

The persistence tests execute the actual importer against an in-memory Frappe boundary. They establish application-rule behavior, but do not prove database locking, actual ERPNext lifecycle, installation, or real-user permission behavior. The source contains five additional integration tests for a real bench; they are outside the 109-test local count.

The 0.3 tests additionally cover shortened routine polling and daily correction cadence, expense-date pagination and saturated ties, recovery from saved expense page checkpoints, idempotent evidence upserts, preservation of accounting links, review flags for changed linked evidence, private receipt deduplication, streamed download size limits, safe endpoint allowlists, catalogue cursors, quote direction and effective bill conversion rates.

## Source and review checks

Official Revolut authentication, pagination/state, transaction schema and webhook-signature documents were consulted. The current official Frappe/ERPNext version-16 Bank Transaction source/schema, password storage, job enqueueing and request-body parsing were also inspected. The current official Docker Containerfile/build documentation and Compose service names were checked. References are linked in README.

Independent static review identified paused-map handling and numerically equal Decimal fingerprint issues; both were reproduced and fixed with regression tests. A separate compatibility inspection identified Frappe v15's JSON/query-string parsing behavior; the webhook endpoint was corrected and tested. Static review also checked the checkpoint/resume logic. The 0.3 independent review identified receipt-sibling starvation and a stale account-state restoration bug; both were reproduced with regression tests and fixed. These reviews are not a penetration test or a substitute for a live deployment.

## Not executed here

- Installing/migrating into a real Frappe/ERPNext v16 site.
- The supplied bench integration tests or GitHub-hosted CI workflows.
- Building/running the ERPNext Docker image, including the new manual GitHub publishing workflow.
- Browser interaction tests against a running ERPNext Desk.
- Real Revolut Sandbox or Production consent, API calls or webhooks.
- Statement/balance comparison, fee interpretation, real accounting reconciliation, concurrency under load, or restore/uninstall testing.

There was no live bench, Docker engine or Revolut credential set in this workspace. The [acceptance checklist](acceptance.md) and GitHub bench workflow make the remaining deployment verification explicit. Version 0.4.0 is a release candidate pending those checks on the target deployment, not a claim of production certification.

## v16 port verification

The version gate, standard banking field snapshot, Python runtime constraint and deployment helper are covered by tests. The helper is tested both when absent from the site's installed-app list and when already installed. An independent review found the pre-install get_attr restriction; the fixed constant import expression is tested through the CLI fallback semantics. Official v16 banking schemas/lifecycle, installer, get_attr/execute, background-job API, password API, request parsing, Page loader and IntegrationTestCase implementation were inspected. These checks do not substitute for a real site install or migration. The custom deployment patch awaits the user's actual Dockerfile/Compose command.
