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

The module also includes an **FBA Inventory Ledger** accessible from the *FBA* menu. A scheduled task runs every 30 minutes to download FBA ledger details from Amazon and store them, preventing duplicate transactions. The ledger download now polls the report status until Amazon marks it as finished before retrieving the document. The ledger report uses the `GET_LEDGER_DETAIL_VIEW_DATA` report type and is returned as a tab‑separated file encoded with CP1252.

For reliable results the ledger request explicitly sets `dataStartTime` and `dataEndTime` in ISO 8601 format. It starts 30 days prior to the most recent stored entry and ends at the time of the request.

Ledger entries mirror the columns returned in the detail report including transaction type, quantity and fulfillment center. Duplicate entries are avoided by enforcing uniqueness on the combination of account, date, FNSKU, event type, reference ID and fulfillment center.

Another scheduled task converts ledger entries into standard Odoo stock moves. It creates two warehouses automatically:

* **FBA Inbound** (`FBAIN`) – used as the source location for `Receipts` events.
* **FBA Transfer** (`FBATR`) – used for `WhseTransfer` movements.

Unprocessed ledger lines generate stock moves between these warehouses based on the event type. Created moves are linked back to the ledger entry so the job can safely run repeatedly without creating duplicates.

The cron job also checks for a product matching each ledger line's MSKU. If none exists, a new storable product is created automatically using the FNSKU as the internal reference. The product stores the ASIN and MSKU so further ledger imports reuse the same item.
