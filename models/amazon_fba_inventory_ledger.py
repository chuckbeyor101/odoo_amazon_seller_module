from odoo import models, fields, api
import logging
import time

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
    _order = 'transaction_date desc'

    account_id = fields.Many2one('amazon.seller.account', required=True, string='Seller Account')
    transaction_id = fields.Char(string='Transaction ID', required=True)
    transaction_type = fields.Char(string='Transaction Type')
    transaction_date = fields.Datetime(string='Transaction Date')
    seller_sku = fields.Char(string='Seller SKU')
    fnsku = fields.Char(string='FNSKU')
    asin = fields.Char(string='ASIN')
    fulfillment_center_id = fields.Char(string='Fulfillment Center')
    quantity = fields.Float(string='Quantity')
    disposition = fields.Char(string='Disposition')
    event_description = fields.Char(string='Event Description')

    _sql_constraints = [
        ('unique_transaction', 'unique(account_id, transaction_id)', 'Transaction already exists for this account.')
    ]

    @api.model
    def cron_fetch_fba_inventory_ledger(self):
        """Cron job to fetch FBA inventory ledger data for all accounts."""
        accounts = self.env['amazon.seller.account'].search([])
        for account in accounts:
            try:
                self._fetch_ledger_for_account(account)
            except Exception as e:
                _logger.error('Failed to fetch ledger for %s: %s', account.name, e)
        return True

    def _fetch_ledger_for_account(self, account):
        """Fetches ledger entries for a single seller account.

        This implementation uses the GET_LEDGER_DETAIL_VIEW_DATA report from the
        Amazon Selling Partner API. The method will create the report, download
        the results and store them in this model while preventing duplicates.
        """
        if Reports is None:
            _logger.error('python-amazon-sp-api is not installed.')
            return

        marketplace = Marketplaces.US
        if account.marketplace:
            marketplace = Marketplaces.__dict__.get(account.marketplace, Marketplaces.US)

        credentials = dict(
            refresh_token=account.refresh_token,
            lwa_app_id=account.app_id,
            lwa_client_secret=account.client_secret
        )

        reports = Reports(credentials=credentials, marketplace=marketplace)

        # Request the inventory ledger report
        report = reports.create_report(reportType='GET_LEDGER_DETAIL_VIEW_DATA').payload
        report_id = report.get('reportId')
        if not report_id:
            _logger.error('No report id returned for account %s', account.name)
            return

        # Poll the report status until processing is complete and a document is available
        report_document_id = None
        for _ in range(20):
            result = reports.get_report(reportId=report_id)
            status = result.payload.get('processingStatus')
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

        # Download the completed report and process its contents
        document_result = reports.get_report_document(report_document_id, download=True)
        # The API returns the report document as a decoded string when download=True
        lines = document_result.payload['document'].splitlines()

        headers = []
        for idx, line in enumerate(lines):
            values = [v.strip() for v in line.split(',')]
            if idx == 0:
                headers = values
                continue
            data = dict(zip(headers, values))
            transaction_id = data.get('transaction-id') or data.get('transactionId')
            if not transaction_id:
                continue
            existing = self.search([
                ('account_id', '=', account.id),
                ('transaction_id', '=', transaction_id)
            ], limit=1)
            if existing:
                continue

            self.create({
                'account_id': account.id,
                'transaction_id': transaction_id,
                'transaction_type': data.get('transaction-type'),
                'transaction_date': data.get('transaction-date'),
                'seller_sku': data.get('sku'),
                'fnsku': data.get('fnsku'),
                'asin': data.get('asin'),
                'fulfillment_center_id': data.get('fulfillment-center-id'),
                'quantity': data.get('quantity'),
                'disposition': data.get('disposition'),
                'event_description': data.get('event-description'),
            })

