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

import logging
import traceback
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from .utils import amazon_utils
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class AmazonFBAInbound(models.Model):
    _name = 'amazon.fba.inbound'
    _description = 'Amazon FBA Inbound'
    _auto = False  # Don't create a database table for this model, since it doesn't store data directly

    @api.model
    def cron_fba_inbound(self):
        """
        Import FBA inbound shipments from Amazon.
        """

        accounts = self.env['amazon.seller.account'].search([('import_fba_inbound_shipments', '=', True)])
        _logger.info('Starting Amazon FBA inbound import cron job for %s account(s)', len(accounts))
        for account in accounts:
            try:
                _logger.info('Importing FBA inbound for account: %s', account.name)

                # Add new inbound shipments to the FBA Inbound location
                self.import_account_fba_inbound(account)


            except Exception as e:
                _logger.error('Error importing FBA inbound for account %s: %s', account.name, str(e))
                _logger.error(traceback.format_exc())
                raise ValidationError(f'Failed to import FBA inbound for account {account.name}: {str(e)} \n{traceback.format_exc()}')

    
    @api.model
    def import_account_fba_inbound(self, account):
        """
        Import FBA inbound shipments for a specific account.
        """
        _logger.debug('Importing FBA inbound shipments for account: %s', account.name)

        # Get FBA Inbound Shipments
        fba_inbound_shipment_items = amazon_utils.fba_list_shipment_items_previous_days(account, days=365)

        if not fba_inbound_shipment_items:
            _logger.info('No FBA inbound shipments found for account: %s', account.name)
            return

        fba_inventory_model = self.env['amazon.fba.inventory']
        fba_wh, fba_inbound_loc, fba_stock_loc, fba_reserved_loc, fba_researching_loc, fba_unfulfillable_loc = fba_inventory_model.get_fba_warehouse()

        for item in fba_inbound_shipment_items:

            shipment_id = item.get('ShipmentId')
            msku = item.get('SellerSKU')
            item_qty = item.get('QuantityShipped')
            if not shipment_id or not msku or not item_qty:
                _logger.warning('Skipping shipment without ShipmentId, SellerSKU or QuantityShipped: %s', item)
                continue

            transfer_name = f'{shipment_id} [{msku}]'

            # Check if the shipment already exists as an internal transfer where the source document (origin)
            # is the shipment ID, and destination is FBA Inbound location
            existing_transfer = self.env['stock.picking'].search([
                ('origin', '=', transfer_name),
                ('picking_type_id', '=', fba_wh.in_type_id.id),
                ('location_dest_id', '=', fba_inbound_loc.id)
            ], limit=1)

            if existing_transfer:
                _logger.info('FBA inbound shipment %s already exists as an internal transfer', transfer_name)
                continue

            # Lookup product by any MSKU - simple and straightforward
            product = self.env['product.template'].find_by_msku(msku)
            
            if not product:
                _logger.warning('No product found for MSKU: %s. Skipping this shipment.', msku)
                continue

            # See if we should skip inventory without cost
            if account.skip_inventory_when_no_product_cost and not product.standard_price:
                _logger.info('Skipping inventory update for product %s because it has no cost', product.name)
                continue

            # Get additional shipment details
            shipment_details = amazon_utils.fba_get_shipment_by_id(shipment_id, account)

            # Determine main warehouse stock location from address map
            from_warehouse_location = self.env['amazon.address.map'].get_warehouse_location_else_create(
                name=shipment_details.get('ShipFromAddress', {}).get('Name', ''),
                address_line1=shipment_details.get('ShipFromAddress', {}).get('AddressLine1', ''),
                address_line2=shipment_details.get('ShipFromAddress', {}).get('AddressLine2', ''),
                city=shipment_details.get('ShipFromAddress', {}).get('City', ''),
                state_or_region=shipment_details.get('ShipFromAddress', {}).get('StateOrProvinceCode', ''),
                postal_code=shipment_details.get('ShipFromAddress', {}).get('PostalCode', ''),
                country_code=shipment_details.get('ShipFromAddress', {}).get('CountryCode', '')
            )   

            # If no warehouse location is found, skip this shipment
            if not from_warehouse_location:
                _logger.warning('No warehouse location found for FBA inbound shipment %s. Skipping this shipment.', transfer_name)
                continue

            # Create a new internal transfer for the FBA inbound shipment
            pick = self.env['stock.picking'].create({
                'picking_type_id': fba_wh.in_type_id.id,
                'location_id': from_warehouse_location.id,
                'location_dest_id': fba_inbound_loc.id,
                'origin': transfer_name,
                'note': f'''
                    FBA Inbound Shipment ID: {shipment_id} |
                    MSKU: {msku} |
                ''',
            })

            move_vals = {
                'name': f"FBA Inbound {shipment_id} - {msku}",
                'product_id': product.id,
                'product_uom_qty': item_qty,
                'quantity': item_qty,
                'availability': item_qty,
                'product_uom': self.env.ref('uom.product_uom_unit').id,
                'location_id': from_warehouse_location.id,
                'location_dest_id': fba_inbound_loc.id,
                'picking_id': pick.id,
            }
            self.env['stock.move'].create(move_vals)

            # Confirm the picking to create the stock moves
            pick.action_confirm()
            _logger.info('Created internal transfer for FBA inbound shipment %s', transfer_name)

            pick.action_assign()
            _logger.info('Assigned stock moves for FBA inbound shipment %s', transfer_name)

            pick.button_validate()
            _logger.info('Validated internal transfer for FBA inbound shipment %s', transfer_name)

