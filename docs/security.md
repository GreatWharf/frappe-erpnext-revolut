# Security and access

[Back to Revolut Bank Feed help](README.md)

## Who can do what

- **System Managers** connect accounts, choose optional data, and review source records.
- **Accounting users** work with the standard ERPNext Bank Transactions they are allowed to see.
- Each connection belongs to one ERPNext Company.

The app requests read-only access from Revolut. It cannot send payments or exchange money.

## How credentials are handled

- Private keys and access tokens are encrypted by ERPNext.
- The private key stays on the ERPNext server; only public connection information is copied to Revolut.
- Receipt files follow the permissions of the related expense record.
- Keep the database, site files, and site encryption key together in backups.

## Good habits

- Use HTTPS and keep the server clock accurate.
- Do not paste tokens, private keys, or returned authorization URLs into tickets, screenshots, or GitHub issues.
- Reconnect the existing connection if Revolut access expires; do not create duplicates.
- Revoke Revolut access before removing the app.
