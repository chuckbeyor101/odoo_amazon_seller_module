"""Utility helpers for interfacing with python-amazon-sp-api."""
from sp_api.base import Marketplaces
from datetime import datetime, timezone, timedelta
from sp_api.api import Reports
from sp_api.base import ReportType
import time
import requests
import logging
import gzip
from io import BytesIO


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


def get_fba_inventory_ledger_summary(marketplace: str, credentials, aggregatedByTimePeriod="DAILY", dataStartTime=None, dataEndTime=None, check_delay: int = 10, debug: bool = False):
    # find marketplace mapped value from settings.py
    sp_marketplace = sp_marketplace_mapper(marketplace)

    # Set default time range if not provided
    if dataStartTime is None:
        # Current time - 5 years
        dataStartTime = (datetime.now(timezone.utc) - timedelta(days=5 * 365)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    if dataEndTime is None:
        # Get current time in UTC and format it
        dataEndTime = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Get Inventory Report
    report_type = ReportType.GET_LEDGER_SUMMARY_VIEW_DATA
    report = Reports(credentials=credentials, marketplace=sp_marketplace)

    report_response = report.create_report(reportType=report_type, dataStartTime=dataStartTime, dataEndTime=dataEndTime, aggregatedByTimePeriod=aggregatedByTimePeriod)
    report_id = report_response.payload.get('reportId')

    # Wait for the report to be generated
    report_data = None
    wait_for_report = True

    if debug:
        logging.info(f"Getting Open Listings Feed. Waiting for report to process...")
        logging.info(f"Report ID: {report_id}")

    while wait_for_report:
        time.sleep(check_delay)
        get_report = report.get_report(reportId=report_id)
        if get_report.payload.get('processingStatus') == 'DONE':
            wait_for_report = False
            report_document_id = get_report.payload.get('reportDocumentId')
            report_document = report.get_report_document(reportDocumentId=report_document_id)

            # Get the report data from the URL, and decode it to a tab separated string
            compressed = requests.get(report_document.payload.get('url')).content
            decompressed = gzip.GzipFile(fileobj=BytesIO(compressed)).read().decode('utf-8')
            # Convert the tab separated string to a list of dictionaries
            lines = decompressed.split('\n')
            headers = lines[0].split('\t')
            report_data = [dict(zip(headers, row.split('\t'))) for row in lines[1:] if row.strip()]

        elif get_report.payload.get('processingStatus') == 'IN_PROGRESS':
            if debug:
                logging.info('Report processing in progress')

        elif get_report.payload.get('processingStatus') == 'IN_QUEUE':
            if debug:
                logging.info('Report processing in queue')

        elif get_report.payload.get('processingStatus') == 'FATAL':
            if debug:
                logging.error('Report processing failed')
            return

    return report_data


def get_fba_inventory_ledger_details(marketplace: str, credentials, dataStartTime=None, dataEndTime=None, check_delay: int = 10, debug: bool = False):

    # find marketplace mapped value from settings.py
    sp_marketplace = sp_marketplace_mapper(marketplace)

    # Set default time range if not provided
    if dataStartTime is None:
        # Current time - 5 years
        dataStartTime = (datetime.now(timezone.utc) - timedelta(days=5 * 365)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    if dataEndTime is None:
        # Get current time and format it
        dataEndTime = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Get Inventory Report
    report_type = ReportType.GET_LEDGER_DETAIL_VIEW_DATA
    report = Reports(credentials=credentials, marketplace=sp_marketplace)

    report_response = report.create_report(reportType=report_type, dataStartTime=dataStartTime, dataEndTime=dataEndTime)
    report_id = report_response.payload.get('reportId')

    # Wait for the report to be generated
    report_data = None
    wait_for_report = True

    if debug:
        logging.info(f"Getting Open Listings Feed. Waiting for report to process...")
        logging.info(f"Report ID: {report_id}")

    while wait_for_report:
        time.sleep(check_delay)
        get_report = report.get_report(reportId=report_id)
        if get_report.payload.get('processingStatus') == 'DONE':
            wait_for_report = False
            report_document_id = get_report.payload.get('reportDocumentId')
            report_document = report.get_report_document(reportDocumentId=report_document_id)

            # Get the report data from the URL, and decode it to a tab separated string
            compressed = requests.get(report_document.payload.get('url')).content
            decompressed = gzip.GzipFile(fileobj=BytesIO(compressed)).read().decode('utf-8')
            # Convert the tab separated string to a list of dictionaries
            lines = decompressed.split('\n')
            headers = lines[0].split('\t')
            report_data = [dict(zip(headers, row.split('\t'))) for row in lines[1:] if row.strip()]

        elif get_report.payload.get('processingStatus') == 'IN_PROGRESS':
            if debug:
                logging.info('Report processing in progress')

        elif get_report.payload.get('processingStatus') == 'IN_QUEUE':
            if debug:
                logging.info('Report processing in queue')

        elif get_report.payload.get('processingStatus') == 'FATAL':
            if debug:
                logging.error('Report processing failed')
            return

    return report_data
