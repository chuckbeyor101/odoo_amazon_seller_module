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

_logger = logging.getLogger(__name__)

class AmazonAWDInbound(models.Model):
    _name = 'amazon.awd.inbound'
    _description = 'Amazon AWD Inbound'
    _auto = False  # Don't create a database table for this model, since it doesn't store data directly

    @api.model
    def cron_awd_inbound(self):
        """
        Import AWD inbound shipments from Amazon.
        """

        accounts = self.env['amazon.seller.account'].search([('import_awd_inbound_shipments', '=', True)])
        _logger.info('Starting Amazon AWD inbound import cron job for %s account(s)', len(accounts))
        for account in accounts:
            try:
                _logger.debug('Importing AWD inbound for account: %s', account.name)

                # Get AWD Inbound Shipments
                awd_inbound_shipments = amazon_utils.awd_list_inbound_shipments(account)

                if not awd_inbound_shipments:
                    _logger.debug('No AWD inbound shipments found for account: %s', account.name)
                    continue

                # Add new inbound shipments to the AWD Inbound location
                self.import_account_awd_inbound(account, awd_inbound_shipments)

            except Exception as e:
                _logger.error('Error importing AWD inbound for account %s: %s', account.name, str(e))
                _logger.error(traceback.format_exc())
                raise ValidationError(f'Failed to import AWD inbound for account {account.name}: {str(e)} \n{traceback.format_exc()}')


    @api.model
    def import_account_awd_inbound(self, account, awd_inbound_shipments):
        
        awd_inventory_model = self.env['amazon.awd.inventory']
        awd_wh, awd_inbound_loc, awd_stock_loc = awd_inventory_model.get_awd_warehouse()

        for shipment in awd_inbound_shipments:
            self.import_shipment(account, shipment, awd_wh, awd_inbound_loc, awd_stock_loc)

    @api.model
    def import_shipment(self, account, shipment, awd_wh, awd_inbound_loc, awd_stock_loc):
        # Check if the shipment already exists as an internal transfer where the source document (origin)
            # is the shipment ID, and destination is AWD Inbound location
            existing_transfer = self.env['stock.picking'].search([
                ('origin', '=', shipment.get('shipmentId')),
                ('picking_type_id', '=', awd_wh.in_type_id.id),
                ('location_dest_id', '=', awd_inbound_loc.id)
            ], limit=1)

            if not shipment.get('shipmentId'):
                _logger.warning('Skipping shipment without ShipmentId: %s', shipment)
                return

            if existing_transfer:
                _logger.debug('AWD inbound shipment %s already exists as an internal transfer', shipment.get('shipmentId'))
                return

            # Get the inbound shipment details
            shipment_details = amazon_utils.awd_get_inbound_shipment_details(account, shipment.get('shipmentId'))
            if not shipment_details:
                _logger.warning('No details found for AWD inbound shipment %s', shipment.get('shipmentId'))
                return

            # Determine main warehouse stock location from address map
            from_warehouse_location = self.env['amazon.address.map'].get_warehouse_location_else_create(
                name=shipment_details.get('originAddress', {}).get('name', ''),
                address_line1=shipment_details.get('originAddress', {}).get('addressLine1', ''),
                address_line2=shipment_details.get('originAddress', {}).get('addressLine2', ''),
                city=shipment_details.get('originAddress', {}).get('city', ''),
                state_or_region=shipment_details.get('originAddress', {}).get('stateOrRegion', ''),
                postal_code=shipment_details.get('originAddress', {}).get('postalCode', ''),
                country_code=shipment_details.get('originAddress', {}).get('countryCode', 'US')
            )   

            # If no warehouse location is found, skip this shipment
            if not from_warehouse_location:
                _logger.warning('No warehouse location found for AWD inbound shipment %s. Skipping this shipment.', shipment.get('shipmentId'))
                return

            # Create a new internal transfer for the AWD inbound shipment
            pick = self.env['stock.picking'].create({
                'picking_type_id': awd_wh.in_type_id.id,
                'location_id': from_warehouse_location.id,
                'location_dest_id': awd_inbound_loc.id,
                'origin': shipment.get('shipmentId'),
                'note': f'''
                    AWD Inbound Shipment ID: {shipment.get('shipmentId')} 
                ''',
            })


            for item in shipment_details.get('shipmentContainerQuantities', []):
                count = item.get('count')
                asin = item.get('distributionPackage', {}).get('contents', {}).get('products', [{}])[0].get('attributes', {})[0].get('value')
                item_qty = item.get('distributionPackage', {}).get('contents', {}).get('products', [{}])[0].get('quantity')

                if not asin or not count or not item_qty:
                    # Stop processing this transfer. Something is wrong with the shipment
                    pick.unlink() # Delete this picking
                    _logger.warning('Skipping item in AWD inbound shipment %s due to missing ASIN, count, or quantity', shipment.get('shipmentId'))
                    return

                for i in range(count):
                    # Create a stock move for each item in the shipment
                    product = self.env['product.product'].search([('amazon_asin', '=', asin)], limit=1)

                    if not product:
                        # Stop processing this transfer. Something is wrong with the shipment
                        pick.unlink() # Delete this picking
                        _logger.warning('Skipping AWD inbound shipment %s due to missing product', shipment.get('shipmentId'))
                        return  
                    
                    # See if we should skip inventory without cost
                    if account.skip_inventory_when_no_product_cost and not product.standard_price:
                        _logger.info('Skipping inventory update for product %s because it has no cost', product.name)
                        return
                    

                    move_vals = {
                        'name': f"AWD Inbound {shipment.get('shipmentId')} - {item.get('sku')}",
                        'product_id': product.id,
                        'product_uom_qty': item_qty,
                        'quantity': item_qty,
                        'availability': item_qty,
                        'product_uom': self.env.ref('uom.product_uom_unit').id,
                        'location_id': from_warehouse_location.id,
                        'location_dest_id': awd_inbound_loc.id,
                        'picking_id': pick.id,
                    }
                    self.env['stock.move'].create(move_vals)

            
            # Confirm the picking to create the stock moves
            pick.action_confirm()
            _logger.info('Created internal transfer for AWD inbound shipment %s', shipment.get('shipmentId'))

            pick.action_assign()
            _logger.info('Assigned stock moves for AWD inbound shipment %s', shipment.get('shipmentId'))

            pick.button_validate()
            _logger.info('Validated internal transfer for AWD inbound shipment %s', shipment.get('shipmentId'))



