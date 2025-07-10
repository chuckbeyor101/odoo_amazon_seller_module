from odoo import models, fields, api
import logging
from datetime import datetime, timedelta

from .utils import amazon_utils

_logger = logging.getLogger(__name__)


class AmazonFbaInventoryLedger(models.Model):
    """Stores FBA inventory ledger transactions for a seller account."""
    _name = 'amazon.fba.inventory.ledger'
    _description = 'Amazon FBA Inventory Ledger'
    _order = 'ledger_date desc'

    account_id = fields.Many2one('amazon.seller.account', required=True, string='Seller Account')
    ledger_date = fields.Date(string='Date')
    fnsku = fields.Char(string='FNSKU')
    asin = fields.Char(string='ASIN')
    msku = fields.Char(string='MSKU')
    title = fields.Char(string='Title')
    event_type = fields.Char(string='Event Type')
    reference_id = fields.Char(string='Reference ID')
    quantity = fields.Float(string='Quantity')
    fulfillment_center = fields.Char(string='Fulfillment Center')
    disposition = fields.Char(string='Disposition')
    reason = fields.Char(string='Reason')
    country = fields.Char(string='Country')
    reconciled_quantity = fields.Float(string='Reconciled Quantity')
    unreconciled_quantity = fields.Float(string='Unreconciled Quantity')
    stock_move_id = fields.Many2one('stock.move', string='Stock Move', readonly=True)

    _sql_constraints = [
        (
            'unique_entry',
            'unique(account_id, ledger_date, fnsku, event_type, reference_id, fulfillment_center)',
            'Ledger entry already exists for this account, date, FNSKU and reference.'
        )
    ]

    @api.model
    def cron_fetch_fba_inventory_ledger(self):
        """Cron job to fetch FBA inventory ledger data for all accounts."""
        accounts = self.env['amazon.seller.account'].search([])
        _logger.info('Starting FBA ledger cron job for %s account(s)', len(accounts))
        for account in accounts:
            try:
                _logger.info('Fetching FBA ledger for account %s', account.name)
                self._fetch_ledger_for_account(account)
            except Exception as e:
                _logger.error('Failed to fetch ledger for %s: %s', account.name, e)
        _logger.info('FBA ledger cron job complete')
        return True

    def _fetch_ledger_for_account(self, account):
        """Fetch ledger entries for a single seller account using amazon_utils."""

        credentials = {
            'refresh_token': account.refresh_token,
            'lwa_app_id': account.app_id,
            'lwa_client_secret': account.client_secret,
        }

        latest_entry = self.search([
            ('account_id', '=', account.id),
        ], order='ledger_date desc', limit=1)
        if latest_entry and latest_entry.ledger_date:
            start_dt = datetime.combine(latest_entry.ledger_date, datetime.min.time())
        else:
            start_dt = datetime.utcnow() - timedelta(days=30)
        end_dt = datetime.utcnow()

        transactions = amazon_utils.get_fba_inventory_ledger_details(
            marketplace=account.marketplace,
            credentials=credentials,
            debug=True
        ) or []

        _logger.info('Fetched %s transactions for account %s', len(transactions), account.name)

        for data in transactions:
            ledger_date = data.get('Date')
            fnsku = data.get('FNSKU')
            if not (ledger_date and fnsku):
                _logger.warning('Skipping entry with missing date or FNSKU: %s', data)
                continue

            # Convert "MM/DD/YYYY" strings to ISO format for Odoo
            # try:
            #     ledger_date_dt = datetime.strptime(ledger_date, '%Y-%m-%d')
            # except Exception:
            try:
                ledger_date_dt = datetime.strptime(ledger_date, '%m/%d/%Y')
            except Exception:
                _logger.debug('Unable to parse date %s', ledger_date)
                continue

            ledger_date = ledger_date_dt.date().isoformat()

            event_type = data.get('EventType') or data.get('Event Type')
            reference_id = data.get('ReferenceID') or data.get('Reference ID')
            fulfillment_center = data.get('FulfillmentCenter') or data.get('Fulfillment Center')

            existing = self.search([
                ('account_id', '=', account.id),
                ('ledger_date', '=', ledger_date),
                ('fnsku', '=', fnsku),
                ('event_type', '=', event_type),
                ('reference_id', '=', reference_id),
                ('fulfillment_center', '=', fulfillment_center),
            ], limit=1)

            if existing:
                _logger.info('Skipping existing entry for %s on %s', fnsku, ledger_date)
                continue

            def to_float(val):
                try:
                    return float(val)
                except Exception:
                    return 0.0

            self.create({
                'account_id': account.id,
                'ledger_date': ledger_date,
                'fnsku': fnsku,
                'asin': data.get('ASIN'),
                'msku': data.get('MSKU'),
                'title': data.get('Title'),
                'event_type': event_type,
                'reference_id': reference_id,
                'quantity': to_float(data.get('Quantity')),
                'fulfillment_center': fulfillment_center,
                'disposition': data.get('Disposition'),
                'reason': data.get('Reason'),
                'country': data.get('Country'),
                'reconciled_quantity': to_float(data.get('ReconciledQuantity') or data.get('Reconciled Quantity')),
                'unreconciled_quantity': to_float(data.get('UnreconciledQuantity') or data.get('Unreconciled Quantity')),
            })

            _logger.info('Created ledger entry for %s on %s', fnsku, ledger_date)

        _logger.info('Completed fetching ledger for account %s', account.name)

    @api.model
    def _ensure_fba_warehouses(self):
        """Ensure FBA warehouses used for ledger transactions exist."""
        Warehouse = self.env['stock.warehouse']
        company = self.env.company

        inbound = Warehouse.search([('code', '=', 'FBAIN'), ('company_id', '=', company.id)], limit=1)
        if not inbound:
            inbound = Warehouse.create({
                'name': 'FBA Inbound',
                'code': 'FBAIN',
                'company_id': company.id,
            })

        transfer = Warehouse.search([('code', '=', 'FBATR'), ('company_id', '=', company.id)], limit=1)
        if not transfer:
            transfer = Warehouse.create({
                'name': 'FBA Transfer',
                'code': 'FBATR',
                'company_id': company.id,
            })

        return inbound, transfer

    @api.model
    def cron_create_inventory_transactions(self):
        """Create Odoo stock moves from unprocessed ledger entries."""
        inbound_wh, transfer_wh = self._ensure_fba_warehouses()

        unprocessed = self.search([('stock_move_id', '=', False)])
        Product = self.env['product.product']
        Template = self.env['product.template']

        for entry in unprocessed:
            product = Product.search([('amazon_asin', '=', entry.asin)], limit=1)
            if not product:
                product = Product.search([('default_code', '=', entry.fnsku)], limit=1)
            if not product:
                vals = {
                    'name': entry.title or entry.asin or entry.fnsku,
                    'type': 'product',
                }
                if 'detailed_type' in Template._fields:
                    vals['detailed_type'] = 'product'
                template = Template.create(vals)
                product = template.product_variant_id
                product.write({
                    'default_code': entry.fnsku,
                    'amazon_asin': entry.asin,
                })

            qty = abs(entry.quantity)
            if qty <= 0:
                continue

            if entry.event_type == 'Receipts':
                src_loc = inbound_wh.lot_stock_id.id
                dest_loc = transfer_wh.lot_stock_id.id
            elif entry.event_type == 'WhseTransfer':
                if entry.quantity > 0:
                    src_loc = inbound_wh.lot_stock_id.id
                    dest_loc = transfer_wh.lot_stock_id.id
                else:
                    src_loc = transfer_wh.lot_stock_id.id
                    dest_loc = inbound_wh.lot_stock_id.id
            else:
                continue

            move = self.env['stock.move'].create({
                'name': f'FBA {entry.event_type}',
                'product_id': product.id,
                'product_uom': product.uom_id.id,
                'product_uom_qty': qty,
                'location_id': src_loc,
                'location_dest_id': dest_loc,
            })
            move._action_confirm()
            move._action_done()
            entry.stock_move_id = move.id

        return True

