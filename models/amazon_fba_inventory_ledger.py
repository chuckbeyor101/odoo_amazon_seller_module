from odoo import models, fields, api
import logging
import time
import requests
import gzip
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

try:
    from sp_api.api import Reports
    from sp_api.base import Marketplaces
except Exception:
    Reports = None
    Marketplaces = None


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
    disposition = fields.Char(string='Disposition')
    starting_balance = fields.Float(string='Starting Warehouse Balance')
    in_transit_between_warehouses = fields.Float(string='In Transit Between Warehouses')
    receipts = fields.Float(string='Receipts')
    customer_shipments = fields.Float(string='Customer Shipments')
    customer_returns = fields.Float(string='Customer Returns')
    vendor_returns = fields.Float(string='Vendor Returns')
    warehouse_transfer = fields.Float(string='Warehouse Transfer In/Out')
    found = fields.Float(string='Found')
    lost = fields.Float(string='Lost')
    damaged = fields.Float(string='Damaged')
    disposed = fields.Float(string='Disposed')
    other_events = fields.Float(string='Other Events')
    ending_balance = fields.Float(string='Ending Warehouse Balance')
    unknown_events = fields.Float(string='Unknown Events')
    location = fields.Char(string='Location')

    _sql_constraints = [
        (
            'unique_entry',
            'unique(account_id, ledger_date, fnsku, location)',
            'Ledger entry already exists for this account, date, FNSKU and location.'
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
        """Fetches ledger entries for a single seller account.

        This implementation uses the GET_LEDGER_SUMMARY_VIEW_DATA report from
        the Amazon Selling Partner API. The method will create the report,
        download the results and store them in this model while preventing
        duplicates.
        """
        if Reports is None:
            _logger.error('python-amazon-sp-api is not installed.')
            return

        marketplace = Marketplaces.US
        if account.marketplace:
            marketplace = Marketplaces.__dict__.get(account.marketplace, Marketplaces.US)
        _logger.info('Using marketplace %s for account %s', marketplace, account.name)

        credentials = dict(
            refresh_token=account.refresh_token,
            lwa_app_id=account.app_id,
            lwa_client_secret=account.client_secret
        )

        reports = Reports(credentials=credentials, marketplace=marketplace)

        # Request the inventory ledger report
        _logger.info('Requesting inventory ledger report for account %s', account.name)

        latest_entry = self.search([
            ('account_id', '=', account.id),
        ], order='ledger_date desc', limit=1)
        if latest_entry and latest_entry.ledger_date:
            start_dt = datetime.combine(latest_entry.ledger_date, datetime.min.time())
        else:
            start_dt = datetime.utcnow() - timedelta(days=30)
        end_dt = datetime.utcnow()

        report = reports.create_report(
            reportType='GET_LEDGER_SUMMARY_VIEW_DATA',
            dataStartTime=start_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            dataEndTime=end_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
        ).payload
        report_id = report.get('reportId')
        if not report_id:
            _logger.error('No report id returned for account %s', account.name)
            return
        _logger.info('Created ledger report %s for account %s', report_id, account.name)

        # Poll the report status until processing is complete and a document is available
        report_document_id = None
        for _ in range(20):
            result = reports.get_report(reportId=report_id)
            status = result.payload.get('processingStatus')
            _logger.debug('Report %s status %s', report_id, status)
            if status == 'DONE':
                report_document_id = result.payload.get('reportDocumentId')
                break
            if status in ('CANCELLED', 'FATAL'):
                _logger.error('Report %s ended with status %s', report_id, status)
                return
            time.sleep(15)

        if not report_document_id:
            _logger.error('No reportDocumentId for report %s', report_id)
            return
        _logger.info('Report %s completed, document %s', report_id, report_document_id)

        # Download the completed report and process its contents
        document_result = reports.get_report_document(report_document_id)
        url = document_result.payload.get('url')
        compression = document_result.payload.get('compressionAlgorithm')
        resp = requests.get(url)
        content = resp.content
        if compression == 'GZIP':
            content = gzip.decompress(content)
        lines = content.decode('cp1252').splitlines()
        _logger.info('Downloaded %s line(s) from inventory ledger report', len(lines))

        headers = []
        for idx, line in enumerate(lines):
            values = [v.strip() for v in line.split('\t')]
            if idx == 0:
                headers = values
                continue
            data = dict(zip(headers, values))
            ledger_date = data.get('Date')
            fnsku = data.get('FNSKU')
            location = data.get('Location')
            if not (ledger_date and fnsku):
                continue
            existing = self.search([
                ('account_id', '=', account.id),
                ('ledger_date', '=', ledger_date),
                ('fnsku', '=', fnsku),
                ('location', '=', location),
            ], limit=1)
            if existing:
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
                'disposition': data.get('Disposition'),
                'starting_balance': to_float(data.get('StartingWarehouseBalance')),
                'in_transit_between_warehouses': to_float(data.get('InTransitBetweenWarehouses')),
                'receipts': to_float(data.get('Receipts')),
                'customer_shipments': to_float(data.get('CustomerShipments')),
                'customer_returns': to_float(data.get('CustomerReturns')),
                'vendor_returns': to_float(data.get('VendorReturns')),
                'warehouse_transfer': to_float(data.get('WarehouseTransferIn/Out')),
                'found': to_float(data.get('Found')),
                'lost': to_float(data.get('Lost')),
                'damaged': to_float(data.get('Damaged')),
                'disposed': to_float(data.get('Disposed')),
                'other_events': to_float(data.get('OtherEvents')),
                'ending_balance': to_float(data.get('EndingWarehouseBalance')),
                'unknown_events': to_float(data.get('UnknownEvents')),
                'location': location,
            })

