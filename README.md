<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/integration-dark.svg" />
    <img src="docs/images/integration-light.svg" alt="ERPNext and Revolut Business" width="480" />
  </picture>
</p>

# Revolut Bank Feed for ERPNext

**Unofficial · Read-only · ERPNext v16 · MIT licensed**

Revolut Bank Feed brings your Revolut Business accounts into ERPNext so you can see transactions, check balances, handle foreign-currency activity, and reconcile your books with less manual work. It was built for internal use at Great Wharf and is shared as an independent community app. It is not affiliated with Revolut or Frappe.

## What you can do

- Connect a Revolut Business account through a guided setup.
- Bring in new transactions automatically every 15 minutes.
- Import older transactions when you need them.
- Match Revolut accounts to your ERPNext Bank Accounts.
- See balances across multiple currencies.
- Review exchange rates, conversions, fees, and FX details where Revolut provides them.
- Import available receipts and expense information.
- Review transactions before reconciling them in ERPNext.
- Keep the connection read-only: ERPNext cannot make payments through this app.

## What you need

- Frappe and ERPNext v16.
- A Revolut Business Grow plan or higher.
- Access to your Revolut Business settings and an ERPNext System Manager account.

## Getting started

1. Install the app on your ERPNext site.
2. Open **Revolut Bank Feed** from the ERPNext home screen, or open **Banking → Connect Revolut**.
3. Follow the short connection guide in ERPNext.
4. Choose your company and import date.
5. Select the Revolut accounts you want to use and match them to ERPNext Bank Accounts.
6. Start the feed, then review the first transactions against your Revolut account.

The app keeps its connection details encrypted on your ERPNext site. Keep your normal database backups and site encryption key safe.

## Installing on a self-hosted bench

```sh
bench get-app https://github.com/GreatWharf/frappe-erpnext-revolut.git
bench --site YOUR_SITE install-app revolut_bank_feed
bench --site YOUR_SITE migrate
bench build --app revolut_bank_feed
```

Frappe Cloud users can install the app from the Marketplace once it is approved.

## How syncing works

The app reads data from Revolut and creates standard ERPNext Bank Transactions. It does not send payments, change Revolut account settings, or create accounting vouchers automatically. Check the first import carefully, especially for foreign-currency payments and fees.

## Help

- [Setup guide](docs/browser-setup.md)
- [Requirements](docs/v16-compatibility.md)
- [Documentation](docs/README.md)
- [Troubleshooting](docs/operations.md)
- [Report an issue](https://github.com/GreatWharf/frappe-erpnext-revolut/issues) — never include credentials or financial data.

## License

This project is MIT licensed. Revolut and ERPNext names and logos belong to their respective owners. See [logo sources](docs/images/README.md).
