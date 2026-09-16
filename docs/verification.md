# Release 0.5.0 verification

## Local checks — 16 September 2026

The release candidate passed **187 offline Python tests** on Python 3.14, the Node Desk behavior checks, Ruff lint/format, and wheel/source builds. Both distribution archives were checked for **78 runtime source/asset files**, including the setup PNG logos. No production credentials or financial data were used.

The new regressions cover explicit skips in mixed-account FX/transfers, unknown-account review, skipped-account persistence and activation races, early-v15 reference field limits, matching v15/v16 gates, version-aware navigation, configuration-lock lifetime, and API commit-before-unlock ordering. Existing tests cover Decimal amounts, duplicate imports, source changes, credentials, webhooks, historical windows, and optional expense/receipt/FX imports.

Node behavior checks execute the actual page/form scripts against a lightweight Desk boundary: registration, escaped account details, explicit selections, pause confirmation/cancellation, grouped actions, and paused-state visibility. This is not a visual review in a live browser.

Reproduce from the repository root:

```sh
python -m pip install -e '.[test]'
python -m pytest -q
node tests/test_desk_loader.cjs
ruff check .
ruff format --check .
find revolut_bank_feed -name '*.js' -print0 | xargs -0 -n1 node --check
python -m build
python scripts/check_dist.py
```

Build into a clean `dist` directory: the archive check intentionally refuses ambiguous multiple-version output.

## Remote compatibility gates

The unit workflow runs on Python **3.10, 3.12 and 3.14**. The integration workflow installs current matching **version-15** and **version-16** Frappe/ERPNext branches, installs the connector, migrates, and runs actual ERPNext Bank Transaction lifecycle tests with synthetic data and MariaDB/Redis.

The real-site suite checks submitted/unreconciled rows, idempotency without GL postings, source-change review, provenance protection, disabled-map history, credential preservation, and Redis exclusion during a configuration transaction. Fixture transaction callbacks are simulated where necessary to keep test records rollbackable; this is not a concurrency load test.

A configured matrix is not a passed matrix. Inspect [GitHub Actions](https://github.com/GreatWharf/frappe-erpnext-revolut/actions) for the exact release commit/tag before deployment. CI tests representative current branches; it does not establish that every historical v15/v16 patch combination has been exercised.

## Still requires site/bank acceptance

- Consent and read access with the customer's actual Revolut Business plan.
- Live browser review, including dark mode, small screens, and the installed Desk theme.
- Bank-statement comparison, fees and FX interpretation, and a complete accounting reconciliation.
- Webhook delivery, scheduler/worker operation, concurrent requests under load, and backup/restore on the target deployment.
- Exact Docker image build and deployment configuration if self-hosted.

No live bench, Docker engine or bank credentials were available locally. Remote CI does not use a live Revolut account. Complete the [acceptance checklist](acceptance.md) and [compatibility requirements](v16-compatibility.md). A source tag is a release candidate, not a production certification or Frappe Marketplace approval.

## Historical evidence

The earlier v16 port recorded 109 passing offline tests on 12 September 2026. That result is superseded by the current local run above and should not be quoted as verification of a newer release. Source inspection of official Frappe/ERPNext schemas, routing, password storage, transaction callbacks and test runners informed the v15/v16 implementation but does not replace executable integration checks.
