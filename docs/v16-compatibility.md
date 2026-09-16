# Frappe and ERPNext compatibility

Release **0.5.0** targets matching **Frappe/ERPNext v15 or v16** on **MariaDB**. It does not upgrade your framework, database, or other apps. Mixed major versions, v14 and v17 are rejected rather than accepted without validation.

| Stack | Python | Navigation | Integration CI target |
| --- | --- | --- | --- |
| Frappe + ERPNext 15.x | 3.10–3.14, subject to your exact framework/dependency versions | `/app/revolut-setup`, app shortcut and System Manager workspace | Current version-15 branches, Python 3.10, Node 20, MariaDB 10.6 |
| Frappe + ERPNext 16.x | 3.14 | `/desk/revolut-setup`, app icon and workspace sidebar | Current version-16 branches, Python 3.14, Node 24, MariaDB 11.8 |

Keep your existing supported runtime configuration. The app's Python range is not a recommendation to switch a working v15 site to Python 3.14. CI exercises representative stacks, not every historical patch release or every possible dependency combination; use current patched upstream releases and check the exact tag's workflow results before deployment.

## Compatibility measures

- Python 3.10-compatible application syntax, with offline CI on Python 3.10, 3.12 and 3.14.
- Version-aware navigation: v15 uses a normal Workspace and never accesses v16-only Workspace Sidebar or Desktop Layout tables. v16 retains its native home icon/sidebar behavior.
- Both versions retain encrypted server-side credentials, standard Bank Transactions, and normal ERPNext reconciliation. Importing a Bank Transaction does not itself create a general-ledger voucher.
- Native Bank Transaction schema snapshots check importer fields against the upstream interfaces. Long reference text is shortened only where the installed field is a length-limited Data field; the full bank source remains in the audit payload.
- Integration tests use the appropriate Frappe test base and Company fixture mechanism for each major version.
- Configuration edits hold the connection mutex until transaction completion. Worker/token-refresh locks remain lexical so an intermediate credential commit does not release a running worker's lock.

## Install and upgrade

On Frappe Cloud, select the compatible app release/branch when it is approved for the Marketplace. A pushed Git tag alone does not publish a Marketplace listing.

For a self-hosted bench, use the release branch or an immutable release commit through your normal app deployment process:

```sh
bench get-app --branch release/0.5.0 https://github.com/GreatWharf/frappe-erpnext-revolut
bench --site <site> install-app revolut_bank_feed
```

For an existing installation, back up the database, private files and encryption key, update the app checkout to the release, and run `bench --site <site> migrate`. Rebuild assets/restart services using your deployment's standard procedure. Existing Bank Transactions, mappings, credentials and audit history must be retained. Review newly skipped accounts in setup after migration; older releases did not persist explicit exclusions.

Docker examples remain **v16 examples**. Do not use a v16 image to upgrade a v15 database as a side effect of adding this app. Image build installs code/dependencies/assets; one deployment initializer performs site installation/migration after the existing database and sites volume are available. The CLI-only `docker/deploy-site.sh` helper is idempotent but is not a distributed deployment coordinator.

## Verification boundary

Offline tests and source inspection are not proof of a successful install, live browser behavior, Revolut consent, complete bank history, concurrency under load, or accounting reconciliation on your site. The [verification notes](verification.md), [Actions results](https://github.com/GreatWharf/frappe-erpnext-revolut/actions), and [acceptance checklist](acceptance.md) distinguish those checks. Real-site CI uses synthetic data and no bank credentials.

## Official interfaces checked

- [Frappe v15 runtime](https://github.com/frappe/frappe/blob/version-15/pyproject.toml) and [v16 runtime](https://github.com/frappe/frappe/blob/version-16/pyproject.toml).
- [ERPNext v15 Bank Transaction](https://github.com/frappe/erpnext/blob/version-15/erpnext/accounts/doctype/bank_transaction/bank_transaction.json) and [v16 Bank Transaction](https://github.com/frappe/erpnext/blob/version-16/erpnext/accounts/doctype/bank_transaction/bank_transaction.json).
- [Frappe installation requirements](https://docs.frappe.io/framework/user/en/installation).
- [Frappe v16 migration guide](https://github.com/frappe/frappe/wiki/Migrating-to-version-16).

Compatibility changes reviewed on 16 September 2026. Pin a tested upstream release/commit in production rather than relying on moving branches.
