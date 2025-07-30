# ######################################################################################################################
#  Amazon Seller Odoo Module Copyright (c) 2025 by Charles L Beyor and Beyotek Inc.
#  is licensed under Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International.
#  To view a copy of this license, visit https://creativecommons.org/licenses/by-nc-sa/4.0/
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  GitHub: https://github.com/chuckbeyor101/odoo_amazon_seller_module
# ######################################################################################################################

"""Utility helpers for interfacing with python-amazon-sp-api."""
import csv

from sp_api.base import Marketplaces, ReportType
from datetime import datetime, timezone, timedelta
from sp_api.api import Reports, AmazonWarehousingAndDistribution, Inventories, CatalogItems, FulfillmentInbound, Orders
from sp_api.util import throttle_retry, load_all_pages

import time
import requests
import logging
import gzip
from io import BytesIO, StringIO

_logger = logging.getLogger(__name__)


def sp_marketplace_mapper(marketplace: str):
    """
    Maps the marketplace string to the corresponding sp_api marketplace object.

    Args:
        marketplace (str): The marketplace string (e.g., 'US', 'CA').

    Returns:
        Marketplaces: The corresponding sp_api marketplace object.
    """

    sp_api_marketplace_mapping = {
        "US": Marketplaces.US,
        "CA": Marketplaces.CA,
        "MX": Marketplaces.MX,
    }

    return sp_api_marketplace_mapping.get(marketplace)


def marketplace_id_mapper(marketplace: str):
    """
    Maps the marketplace string to the corresponding marketplace ID.

    Args:
        marketplace (str): The marketplace string (e.g., 'US', 'CA').

    Returns:
        str: The corresponding marketplace ID.
    """

    sp_api_marketplace_id_mapping = {
        "US": "ATVPDKIKX0DER",
        "CA": "A2EUQ1WTGCTBG2"
    }

    return sp_api_marketplace_id_mapping.get(marketplace)


def get_credentials_from_account(account):
    credentials = {
            'refresh_token': account.refresh_token,
            'lwa_app_id': account.app_id,
            'lwa_client_secret': account.client_secret,
        }
    return credentials


@throttle_retry()
def get_catalog_item(account, asin):

    credentials = get_credentials_from_account(account)
    sp_marketplace = sp_marketplace_mapper(account.marketplace)

    catalog_items = CatalogItems(credentials=credentials, marketplace=sp_marketplace)
    response = catalog_items.get_catalog_item(asin=asin, includedData=['attributes', 'summaries'])

    if response.payload:
        return response.payload
    else:
        logging.error("No catalog item found or error occurred.")
        return {}


def get_open_listings(account):

    # Get credentials and marketplace from the account
    credentials = get_credentials_from_account(account)
    sp_marketplace = sp_marketplace_mapper(account.marketplace)

    # Create Inventory Report
    report_type = ReportType.GET_FLAT_FILE_OPEN_LISTINGS_DATA
    report = Reports(credentials=credentials, marketplace=sp_marketplace)
    report_response = report.create_report(reportType=report_type)
    report_id = report_response.payload.get('reportId')

    # Wait for the report to be generated
    report_data = None
    wait_for_report = True

    logging.info(f"Getting Open Listings Feed. Waiting for report to process...")
    while wait_for_report:
        time.sleep(10)
        get_report = report.get_report(reportId=report_id)
        if get_report.payload.get('processingStatus') == 'DONE':
            wait_for_report = False
            report_document_id = get_report.payload.get('reportDocumentId')
            report_document = report.get_report_document(reportDocumentId=report_document_id)

            # Get the report data from the URL, and decode it to a tab separated string
            report_data = requests.get(report_document.payload.get('url')).content.decode('cp1252')

            # Convert the tab separated string to a list of dictionaries
            report_data = [dict(zip(report_data.split('\n')[0].split('\t'), row.split('\t'))) for row in
                           report_data.split('\n')[1:]]

        elif get_report.payload.get('processingStatus') == 'IN_PROGRESS':
            pass

        elif get_report.payload.get('processingStatus') == 'IN_QUEUE':
            logging.debug('Report processing in queue')

        elif get_report.payload.get('processingStatus') == 'FATAL':
            logging.error('Report processing failed')
            return
    return report_data


def list_all_awd_inventory(amz_account):
    """ Lists all inventory items in Amazon Warehousing and Distribution (AWD)."""

    credentials = get_credentials_from_account(amz_account)
    sp_marketplace = sp_marketplace_mapper(amz_account.marketplace)

    awd_inventory_list = []

    
    @load_all_pages()
    @throttle_retry()
    def _list_inventory():
        return AmazonWarehousingAndDistribution(credentials=credentials, marketplace=sp_marketplace).list_inventory()

    for page in _list_inventory():
        awd_inventory_list.extend(page.payload.get('inventory', []))

    return awd_inventory_list


@throttle_retry()
def get_fba_inventory_summary_by_sku(seller_sku, account):
    credentials = get_credentials_from_account(account)
    sp_marketplace = sp_marketplace_mapper(account.marketplace)

    inventory_summary = Inventories(credentials=credentials, marketplace=sp_marketplace).get_inventory_summary_marketplace(sellerSkus=[seller_sku], details=True)
    
    if len(inventory_summary.payload.get('inventorySummaries', []))>0:
        return inventory_summary.payload.get('inventorySummaries', [])[0]
  
    return None
    

def get_orders_recently_updated(account, days:int=30, **kwargs):
    credentials = get_credentials_from_account(account)
    sp_marketplace = sp_marketplace_mapper(account.marketplace)

    # Get Orders
    orders_api = Orders(credentials=credentials, marketplace=sp_marketplace)

    LastUpdatedAfter = (datetime.utcnow() - timedelta(days=days)).isoformat().replace("+00:00", "Z")

    @load_all_pages()
    @throttle_retry() 
    def load_orders(**kwargs):
        return orders_api.get_orders(**kwargs)

    orders = []
    for page in load_orders(LastUpdatedAfter=LastUpdatedAfter, **kwargs):
        for order in page.payload.get('Orders', []):
            orders.append(order)

    return orders

def get_order_items(account, order_id):
    credentials = get_credentials_from_account(account)
    sp_marketplace = sp_marketplace_mapper(account.marketplace)

    # Get Order Details
    orders_api = Orders(credentials=credentials, marketplace=sp_marketplace)

    @load_all_pages()
    @throttle_retry()
    def get_order_items():
        return orders_api.get_order_items(order_id=order_id)

    order_items = []
    for page in get_order_items():
        for item in page.payload.get('OrderItems', []):
            order_items.append(item)

    return order_items


def awd_list_inbound_shipments(account, **kwargs):

    # Get credentials and marketplace from the account
    credentials = get_credentials_from_account(account)
    sp_marketplace = sp_marketplace_mapper(account.marketplace)

    # Get Inbound Shipments
    awd = AmazonWarehousingAndDistribution(credentials=credentials, marketplace=sp_marketplace)

    @throttle_retry()
    @load_all_pages()
    def get_shipments(**kwargs):
        return awd.list_inbound_shipments(**kwargs, maxResults=200)

    shipments = []

    for page in get_shipments(**kwargs):
        for shipment in page.payload.get('shipments', []):
            shipments.append(shipment)

    return shipments


def awd_get_inbound_shipment_details(account, shipment_id, **kwargs):

    # Get credentials and marketplace from the account
    credentials = get_credentials_from_account(account)
    sp_marketplace = sp_marketplace_mapper(account.marketplace)

    # Get Inbound Shipment
    awd = AmazonWarehousingAndDistribution(credentials=credentials, marketplace=sp_marketplace)

    @throttle_retry()
    def get_shipment():
        return awd.get_inbound_shipment(shipmentId=shipment_id, **kwargs)

    response = get_shipment()

    if response.payload:
        return response.payload
    else:
        logging.error("No shipment found or error occurred.")
        return {}


# def fba_list_shipment_items_previous_days(account, days:int=365, **kwargs):
#     """
#     Fetches a list of inbound shipments from FBA.
#     """
#     # Get credentials and marketplace from the account
#     credentials = get_credentials_from_account(account)
#     sp_marketplace = sp_marketplace_mapper(account.marketplace)

#     # Get Inbound Shipments
#     fba = FulfillmentInbound(credentials=credentials, marketplace=sp_marketplace)

    
#     @load_all_pages(next_token_param="NextToken", extras=dict(QueryType='NEXT_TOKEN'))
#     @throttle_retry()
#     def get_shipment_items(**kwargs):
#         return fba.shipment_items(**kwargs)

#     items = []

#     for page in get_shipment_items(
#         QueryType='DATE_RANGE',
#         LastUpdatedAfter=(datetime.utcnow() - timedelta(days=days)).isoformat().replace("+00:00", "Z"),
#         LastUpdatedBefore=datetime.utcnow().isoformat().replace("+00:00", "Z"),
#     ):
#         for item in page.payload.get('ItemData', []):
#             items.append(item)

#     return items

def fba_inbound_shipments_previous_days(account, days:int=365, shipmentStatusList:list=['WORKING', 'SHIPPED', 'RECEIVING', 'CANCELLED', 'DELETED', 'CLOSED', 'ERROR', 'IN_TRANSIT', 'DELIVERED', 'CHECKED_IN']):
    """
    Fetches a list of inbound shipments from FBA.
    """
    # Get credentials and marketplace from the account
    credentials = get_credentials_from_account(account)
    sp_marketplace = sp_marketplace_mapper(account.marketplace)

    # Get Inbound Shipments
    fba = FulfillmentInbound(credentials=credentials, marketplace=sp_marketplace)

    
    @load_all_pages(next_token_param="NextToken", extras=dict(QueryType='NEXT_TOKEN'))
    @throttle_retry()
    def get_shipments(**kwargs):
        return fba.get_shipments(**kwargs)

    shipments = []

    for page in get_shipments(
        QueryType='DATE_RANGE',
        LastUpdatedAfter=(datetime.utcnow() - timedelta(days=days)).isoformat().replace("+00:00", "Z"),
        LastUpdatedBefore=datetime.utcnow().isoformat().replace("+00:00", "Z"),
        ShipmentStatusList=','.join(shipmentStatusList)):
        for shipment in page.payload.get('ShipmentData', []):
            shipments.append(shipment)

    return shipments

def fba_get_shipment_items_by_shipment_id(account, shipment_id, **kwargs):
    """
    Fetches shipment items for a given shipment ID from FBA.
    """
    # Get credentials and marketplace from the account
    credentials = get_credentials_from_account(account)
    sp_marketplace = sp_marketplace_mapper(account.marketplace)

    # Get Shipment Items
    fba = FulfillmentInbound(credentials=credentials, marketplace=sp_marketplace)

    @throttle_retry()
    def get_shipment_items():
        return fba.shipment_items_by_shipment(shipment_id=shipment_id, **kwargs)

    shipment_items = get_shipment_items().payload.get('ItemData', [])

    return shipment_items


# def fba_get_shipment_by_id(shipment_id, account, **kwargs):
#     """
#     Fetches details of a specific shipment by ID from FBA.
#     """
#     # Get credentials and marketplace from the account
#     credentials = get_credentials_from_account(account)
#     sp_marketplace = sp_marketplace_mapper(account.marketplace)

#     # Get Shipment
#     fba = FulfillmentInbound(credentials=credentials, marketplace=sp_marketplace)

#     @throttle_retry()
#     def get_shipment():
#         return fba.get_shipments_by_id(shipment_id, **kwargs)

#     response = get_shipment()

#     if response.payload:
#         return response.payload.get('ShipmentData', [])[0] if response.payload.get('ShipmentData') else {}
#     else:
#         logging.error("No shipment found or error occurred.")
#         return {}

# def get_or_create_shipping_cost_product(env, account):

#     delivery_product = env['product.product'].search([('name', '=', 'Shipping Cost')], limit=1)

#     # Or create a new one if it doesn't exist
#     if not delivery_product:
#         delivery_product = env['product.product'].create({
#             'name': 'Shipping Cost',
#             'type': 'service',
#             'invoice_policy': 'order', # Or 'delivery' depending on your invoicing policy
#             'list_price': 0.0,
#             'standard_price': 0.0,
#             'taxes_id': [(6, 0, [])],  # Assuming no taxes are applied
#             'purchase_taxes_id': [(6, 0, [])],  # Assuming no taxes are applied
#         })

#     return delivery_product



# def get_fba_inventory_ledger_summary(account, aggregatedByTimePeriod="DAILY", dataStartTime=None, dataEndTime=None, check_delay: int = 10, debug: bool = False):
#     credentials = get_credentials_from_account(account)
#     sp_marketplace = sp_marketplace_mapper(account.marketplace)

#     # Set default time range if not provided
#     if dataStartTime is None:
#         # Current time - 5 years
#         dataStartTime = (datetime.now(timezone.utc) - timedelta(days=5 * 30)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

#     if dataEndTime is None:
#         # Get current time in UTC and format it
#         dataEndTime = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")

#     # Get Inventory Report
#     report_type = ReportType.GET_LEDGER_SUMMARY_VIEW_DATA
#     report = Reports(credentials=credentials, marketplace=sp_marketplace)

#     report_response = report.create_report(reportType=report_type, dataStartTime=dataStartTime, dataEndTime=dataEndTime, 
#                                            reportOptions={"aggregateByLocation":"COUNTRY","aggregatedByTimePeriod":aggregatedByTimePeriod})
#     report_id = report_response.payload.get('reportId')

#     # Wait for the report to be generated
#     report_data = None
#     wait_for_report = True

#     if debug:
#         logging.info(f"Getting Inventory Ledger Summary Feed. Waiting for report to process...")
#         logging.info(f"Report ID: {report_id}")

#     while wait_for_report:
#         time.sleep(check_delay)
#         get_report = report.get_report(reportId=report_id)
#         if get_report.payload.get('processingStatus') == 'DONE':
#             wait_for_report = False
#             report_document_id = get_report.payload.get('reportDocumentId')
#             report_document = report.get_report_document(reportDocumentId=report_document_id)

#             # Get the report data from the URL, and decode it to a tab separated string
#             compressed = requests.get(report_document.payload.get('url')).content
#             decompressed = gzip.GzipFile(fileobj=BytesIO(compressed)).read().decode('utf-8')
#             # Convert the tab separated string to a list of dictionaries
#             lines = decompressed.split('\n')
#             headers = lines[0].split('\t')
#             reader = csv.DictReader(StringIO(decompressed), delimiter='\t')
#             report_data = [dict(row) for row in reader]

#         elif get_report.payload.get('processingStatus') == 'IN_PROGRESS':
#             if debug:
#                 logging.info('Report processing in progress')

#         elif get_report.payload.get('processingStatus') == 'IN_QUEUE':
#             if debug:
#                 logging.info('Report processing in queue')

#         elif get_report.payload.get('processingStatus') == 'FATAL':
#             if debug:
#                 logging.error('Report processing failed')
#             return

#     return report_data


# def get_fba_inventory_ledger_details(account, dataStartTime=None, dataEndTime=None, check_delay: int = 10, debug: bool = False):

#     credentials = get_credentials_from_account(account)
#     sp_marketplace = sp_marketplace_mapper(account.marketplace)

#     # Set default time range if not provided
#     if dataStartTime is None:
#         # Current time - 5 years
#         dataStartTime = (datetime.now(timezone.utc) - timedelta(days=5 * 365)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
#     if dataEndTime is None:
#         # Get current time and format it
#         dataEndTime = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

#     # Get Inventory Report
#     report_type = ReportType.GET_LEDGER_DETAIL_VIEW_DATA
#     report = Reports(credentials=credentials, marketplace=sp_marketplace)

#     report_response = report.create_report(reportType=report_type, dataStartTime=dataStartTime, dataEndTime=dataEndTime)
#     report_id = report_response.payload.get('reportId')

#     # Wait for the report to be generated
#     report_data = None
#     wait_for_report = True

#     if debug:
#         logging.info(f"Getting Inventory Ledger Details Feed. Waiting for report to process...")
#         logging.info(f"Report ID: {report_id}")

#     while wait_for_report:
#         time.sleep(check_delay)
#         get_report = report.get_report(reportId=report_id)
#         if get_report.payload.get('processingStatus') == 'DONE':
#             wait_for_report = False
#             report_document_id = get_report.payload.get('reportDocumentId')
#             report_document = report.get_report_document(reportDocumentId=report_document_id)

#             # Get the report data from the URL, and decode it to a tab separated string
#             compressed = requests.get(report_document.payload.get('url')).content
#             decompressed = gzip.GzipFile(fileobj=BytesIO(compressed)).read().decode('utf-8')
#             # Convert the tab separated string to a list of dictionaries
#             lines = decompressed.split('\n')
#             headers = lines[0].split('\t')
#             reader = csv.DictReader(StringIO(decompressed), delimiter='\t')
#             report_data = [dict(row) for row in reader]

#         elif get_report.payload.get('processingStatus') == 'IN_PROGRESS':
#             if debug:
#                 logging.info('Report processing in progress')

#         elif get_report.payload.get('processingStatus') == 'IN_QUEUE':
#             if debug:
#                 logging.info('Report processing in queue')

#         elif get_report.payload.get('processingStatus') == 'FATAL':
#             if debug:
#                 logging.error('Report processing failed')
#             return

#     return report_data


