# Exchange rates

[All guides](README.md)

Exchange-rate quotes are already included as an optional feature. No separate app is needed.

## Turn them on

1. Finish connecting and activate the bank feed.
2. Open **Connect Revolut → Choose extra data**.
3. Enable **Daily FX quotes** and save.
4. Click **Refresh extra data**, then open **FX quotes** after the job finishes.

## Use a rate in ERPNext

1. Open today’s quote and check its currency direction, rate and fee.
2. Click **Use in Currency Exchange**.
3. Confirm to create an ERPNext **Currency Exchange** record.

You need permission to create Currency Exchange records. Saving a rate does not exchange any money.

## What the quote means

- Direction: each active Revolut account currency **→ your Company’s base currency**.
- Amount: a sell quote for **one unit**, with the fee shown separately.
- Example: for a GBP Company with an active EUR account, the app fetches **EUR → GBP**.
- Quotes are fetched at most once per 24 hours; manual refresh does not bypass that limit.
- Only a quote dated **today in UTC** can be saved to Currency Exchange.

## Before saving

- ERPNext Currency Exchange records apply **site-wide**, across Companies.
- The app never overwrites an existing rate for the same date and direction.
- A quote is indicative. It is not the historical rate used on a bank transaction or a guarantee of the price for a larger exchange.
- Saved rates are not automatically replaced by later quotes.

No quotes? Check that the feed is active, **Daily FX quotes** is enabled, and Revolut has an active account in a currency different from your Company’s base currency. Then check the extra-data status in **Sync logs**.

[Revolut’s exchange-rate guide](https://developer.revolut.com/docs/guides/manage-accounts/exchange-money) · [Data coverage](read-only-coverage.md)
