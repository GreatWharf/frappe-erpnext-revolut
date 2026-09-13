<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/integration-dark.svg" />
    <img src="docs/images/integration-light.svg" alt="ERPNext ↔ Revolut Business" width="480" />
  </picture>
</p>

# Revolut Bank Feed for ERPNext

**Unofficial · Read-only · ERPNext v16 · [MIT License](LICENSE)**

- Import Revolut Business transactions into ERPNext.
- Reconcile them using ERPNext’s standard Bank Reconciliation.
- Built by Great Wharf for internal use and shared publicly.
- Independent project. Not affiliated with or endorsed by Revolut or Frappe.
- **Release candidate:** validate on staging before using live accounts.

## Features

- Browser setup with certificate generation and Revolut authorization.
- Match Revolut accounts to ERPNext Bank Accounts by currency.
- Automatic sync every 15 minutes.
- Sync now, pause, and import older transactions.
- View sync logs and transactions needing review.
- Optional expenses, receipts, balances, and FX data.
- No payment initiation or automatic accounting vouchers.

## Install with Docker

1. Add this entry to your existing image’s app list:

   ```json
   {
     "url": "https://github.com/GreatWharf/erpnext_revolut",
     "branch": "main"
   }
   ```

2. Rebuild the image, keeping your existing apps.
3. Back up your site and deploy the image to all Frappe services.
4. Register the app, install it on the site, and run migration.
5. Check that the scheduler and `long` worker are running.

- [Full Docker instructions](docker/INTEGRATE-EXISTING-DEPLOYMENT.md)
- [Requirements and compatibility](docs/v16-compatibility.md)

## Connect your account

Requires **Revolut Business Grow or above**. [Revolut API requirements](https://help.revolut.com/business/help/integrating-with-external-apps/revolut-business-api/question-using-revolut-business-api/).

1. Open **Revolut Bank Feed** from Home, or **Banking → Connect Revolut**.
2. Choose your Company, environment, and import start date.
3. Click **Create certificate**.
4. In Revolut Business → **Settings → APIs → Business API**, register the public certificate and redirect URL shown.
5. Paste Revolut’s **Client ID** into the setup screen.
6. Approve **READ access**, then paste the returned URL into the wizard within two minutes.
7. Match your bank accounts, check a small import against your statement, and activate the feed.

- Uses a certificate and OAuth; no API key to paste into Docker.
- Private keys and tokens are stored encrypted in ERPNext.
- [Step-by-step setup](docs/browser-setup.md)

## Finding your way around

- Direct setup route: `/desk/revolut-setup`.
- **Home → Revolut Bank Feed:** connection, account mappings, and sync logs.
- **Accounting → Banking → Connect Revolut:** set up or manage the feed.
- **Banking → Banking app:** ERPNext’s separate reconciliation screen, with a Home link back to Desk.
- Seeing Bank Accounts does not mean transactions have synced. Finish authorization, map accounts, and start the feed first.

## Before going live

- Test installation and authorization on staging.
- Compare imported amounts, dates, currencies, and fees with a Revolut statement.
- Keep the database and site encryption key backed up.
- [Validation checklist](docs/acceptance.md) · [Test report](docs/verification.md)

## More help

- [Documentation home](docs/README.md)
- [Exchange rates](docs/exchange-rates.md)

- [Data coverage](docs/read-only-coverage.md)
- [Troubleshooting and upgrades](docs/operations.md)
- [Security](docs/security.md)
- [Report an issue](https://github.com/GreatWharf/erpnext_revolut/issues)

## License

- Code: [MIT](LICENSE).
- ERPNext and Revolut logos belong to their respective owners. [Logo sources](docs/images/README.md).
