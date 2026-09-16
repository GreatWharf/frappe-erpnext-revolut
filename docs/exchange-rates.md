# Exchange rates

[Back to Revolut Bank Feed help](README.md)

Revolut FX quotes are optional. They help you review a rate in ERPNext; they do not exchange money or change a bank transaction.

## Turn on FX quotes

1. Open the active connection in **Connect Revolut**.
2. Choose **Choose extra data**.
3. Turn on **Daily FX quotes** and save.
4. Choose **Refresh extra data**, then open **FX quotes** when the job finishes.

## Save a quote in ERPNext

1. Open today's quote and check the currency direction, rate, and fee.
2. Choose **Use in Currency Exchange**.
3. Review the details and confirm.

The quote is for one unit of the account currency into your Company's base currency. For example, a GBP Company with a EUR account gets a EUR → GBP quote.

## Important limits

- Quotes are refreshed at most once every 24 hours.
- Only today's UTC quote can be saved as a Currency Exchange record.
- ERPNext Currency Exchange records are shared across the site and Companies.
- Existing rates are not overwritten.
- A quote is indicative; it is not the historical rate used for a particular payment.

If no quote appears, check that the feed is active, FX quotes are enabled, and the account currencies differ from the Company's base currency.
