# v16 compatibility and deployment boundary

Release 0.4 targets **Frappe 16.x and ERPNext 16.x**, Python **3.14.x** and Node **24+** for assets. Upstream's current installation guide lists MariaDB **11.8** for v16; this connector supports MariaDB-backed sites. These are compatibility targets, not an instruction to change a working database in place. Match the existing supported v16 release/runtime configuration when integrating the app.

Release 0.3 remains the v15 package. The 0.4 installer rejects v15, mixed majors and other framework majors. It does not upgrade Frappe, ERPNext, MariaDB or the site's other apps.

## Changes made

- The guided page and app navigation use `/desk/revolut-setup`. A v16 desktop app hook points System Managers to it and returns an explicit permission boolean. The old `/app` documentation is replaced for current setup paths.
- The Page script uses its own closure and registers Frappe handlers; it does not depend on global class variables. v16's Page script wrapping is therefore compatible with this structure.
- DocTypes sort by `creation`, following the v16 index/sorting change. Cursor and pending-work queries retain their explicit ordering.
- Checked actual v16 Bank Transaction, Bank Account and Currency Exchange schemas. The bank feed continues inserting/submitting standard Bank Transactions; payment/reconciliation links remain empty until accounting acts. v16 adds transaction-rule fields and reconciliation-type metadata; the connector leaves those native features to ERPNext. Its existing rules may act on imported rows according to your site's configuration; this app neither enables those rules nor creates vouchers itself.
- Document-event guards and controllers do not commit transactions. Worker/API transaction boundaries remain outside the v16 restricted document hooks.
- Verified the v16 query APIs accept the app's list, pluck, page-length and filter forms; singleton boolean settings use integer conversion. Password encryption, job IDs/deduplication and webhook query-string access retain the inspected interfaces.
- The bench tests now use `frappe.tests.IntegrationTestCase`, `EXTRA_TEST_RECORD_DEPENDENCIES` and the superclass setup lifecycle.
- Optional CI/build examples target Python 3.14, Node 24 and MariaDB 11.8. GitHub Actions is not required for a custom Docker deployment.

## Automatic site initialization

The source/dependencies/assets go in the **image build**. The site tables and installed-app registration happen in the **deployment initializer**, after the existing database and sites volume are available. `docker/deploy-site.sh` runs a CLI-only helper, installing only if missing and then invoking migration (or deferring that to your existing migration job).

Frappe v16 rejects normal `get_attr` resolution for an app that is not yet installed. The script uses a fixed explicit import expression through `bench execute` for this first-install case. The site name is a separately quoted shell argument; it is never interpolated as Python code. The helper is not whitelisted or exposed as an HTTP endpoint. It requires an initialized site and Administrator context, checks that ERPNext is already installed, and uses Frappe's standard installer. Exactly one deployment initializer should run per site; this is idempotent execution, not a distributed deployment coordinator.

The deployment owner must handle backups, maintenance, worker draining, database readiness and success-dependent startup. The script must not be run from every web/worker entrypoint. The exact integration will be tailored to the existing Dockerfile/Compose files instead of replacing them.

## Verification limits

Local tests run under Python 3.14.7. Desk scripts are syntax checked with Node 24.19.0. The native banking field snapshot in `tests/fixtures/v16_fields.json` is derived from official version-16 schemas and checks importer fields against that interface. Real Frappe/ERPNext v16 migration, reconciliation, permissions, scheduler, Docker build and Revolut integration remain to be validated on staging. No claim is made that the user's deployment has been changed or tested.

## Official sources

- [Frappe v16 migration guide](https://github.com/frappe/frappe/wiki/Migrating-to-version-16).
- [ERPNext v16 migration guide](https://github.com/frappe/erpnext/wiki/Migration-Guide-to-ERPNext-version-16).
- [Frappe installation requirements](https://docs.frappe.io/framework/user/en/installation).
- [v16 runtime dependencies](https://github.com/frappe/frappe/blob/version-16/pyproject.toml).
- [Bank Transaction lifecycle](https://github.com/frappe/erpnext/blob/version-16/erpnext/accounts/doctype/bank_transaction/bank_transaction.py).
- [Site installer](https://github.com/frappe/frappe/blob/version-16/frappe/installer.py) and [CLI execute implementation](https://github.com/frappe/frappe/blob/version-16/frappe/commands/utils.py).

Sources checked on 2026-09-12. For reproducible deployment, pin compatible release tags/commits from your current stack rather than relying on moving branches.
