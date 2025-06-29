# Amazon Seller Module

This Odoo module provides a basic framework for managing multiple Amazon
seller accounts. Each account stores the following credentials:

- **App ID**
- **Client Secret**
- **Refresh Token**
- **Seller ID**
- **Marketplace** - selectable region where the account operates

The module attempts to install the `python-amazon-sp-api` package during installation.
After configuring an account, use the *Verify Connection* button to test your credentials.
You can also click *Verify & Save* to validate the connection and persist the record in one step.

The module also includes an **FBA Inventory Ledger** accessible from the *FBA* menu. A scheduled task runs every 30 minutes to download FBA ledger details from Amazon and store them, preventing duplicate transactions. The ledger download now polls the report status until Amazon marks it as finished before retrieving the document. The ledger report uses the `GET_LEDGER_SUMMARY_VIEW_DATA` report type and is returned as a tab‑separated file encoded with CP1252.

Ledger entries mirror the columns returned in the summary report including balances and counts for each FNSKU, date and location. Duplicate entries are avoided by enforcing uniqueness on the combination of account, date, FNSKU and location.
