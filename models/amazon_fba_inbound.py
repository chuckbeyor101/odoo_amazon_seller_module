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

        fba_inventory_model = self.env['amazon.fba.inventory']
        fba_wh, fba_inbound_loc, fba_stock_loc, fba_reserved_loc, fba_researching_loc, fba_unfulfillable_loc = fba_inventory_model.get_fba_warehouse()

        inbound_shipment_list = amazon_utils.fba_inbound_shipments_previous_days(account, days=365)

        if not inbound_shipment_list:
            _logger.info('No FBA inbound shipments found for account: %s', account.name)
            return
        
        for shipment in inbound_shipment_list:
            self.import_fba_inbound_shipment(account, shipment, fba_inbound_loc, fba_wh)


    def import_fba_inbound_shipment(self, account, shipment, fba_inbound_loc, fba_wh):

        shipment_id = shipment.get('ShipmentId')
        transfer_name = f'{shipment_id}'

        if not shipment_id:
            _logger.warning('Skipping shipment without ShipmentId: %s', shipment)
            return

        # Check if the picking already exists for shipment
        existing_pick = self.env['stock.picking'].search([
            ('origin', '=', transfer_name),
        ], limit=1)

        if existing_pick:
            self.check_for_cancelled_fba_inbound_shipment(existing_pick, shipment, transfer_name, fba_wh)
            _logger.debug('FBA inbound shipment %s already exists as a stock picking', transfer_name)
            return

        # Determine main warehouse stock location from address map
        from_warehouse_location = self.env['amazon.address.map'].get_warehouse_location_else_create(
            name=shipment.get('ShipFromAddress', {}).get('Name', ''),
            address_line1=shipment.get('ShipFromAddress', {}).get('AddressLine1', ''),
            address_line2=shipment.get('ShipFromAddress', {}).get('AddressLine2', ''),
            city=shipment.get('ShipFromAddress', {}).get('City', ''),
            state_or_region=shipment.get('ShipFromAddress', {}).get('StateOrProvinceCode', ''),
            postal_code=shipment.get('ShipFromAddress', {}).get('PostalCode', ''),
            country_code=shipment.get('ShipFromAddress', {}).get('CountryCode', '')
        ) 

        # If no warehouse location is found, skip this shipment
        if not from_warehouse_location:
            _logger.warning(f'No warehouse location found for FBA inbound shipment {transfer_name}. warehouse: {shipment.get("ShipFromAddress", {}).get("Name", "")} Skipping this shipment. ')
            return

        from_wh = from_warehouse_location.warehouse_id

        if not from_wh:
            _logger.warning(f'No warehouse found for FBA inbound shipment {transfer_name}. warehouse: {shipment.get("ShipFromAddress", {}).get("Name", "")} Skipping this shipment.')
            return

        # Create delivery from the source warehouse to the FBA Transit location
        fba_transit_loc = self.get_fba_transit_loc()
        pick_vals = { # Setting pick values but not creating until we ensure product moves have no issues
            'picking_type_id': from_wh.out_type_id.id,
            'location_id': from_warehouse_location.id,
            'location_dest_id': fba_transit_loc.id,
            'origin': transfer_name,
            'note': f'''
                FBA Inbound Shipment ID: {shipment_id}
            ''',
        }

        # Get shipment items
        shipment_items = amazon_utils.fba_get_shipment_items_by_shipment_id(account, shipment_id)

        if not shipment_items:
            _logger.warning('No shipment items found for FBA inbound shipment %s. Skipping this shipment.', transfer_name)
            return

        # Create the stock picking for the transfer
        moves_queue = []
        for item in shipment_items:
            msku = item.get('SellerSKU')
            item_qty = item.get('QuantityShipped')

            if not msku or not item_qty:
                _logger.warning('Skipping shipment item without SellerSKU or QuantityShipped: %s', item)
                return

            # Lookup product by any MSKU
            product = self.env['product.template'].find_by_msku(msku)

            if not product:
                _logger.warning(f'Skipping shipment {transfer_name} because product with MSKU {msku} not found.')
                return

            # See if we should skip inventory without cost
            if account.skip_inventory_when_no_product_cost and not product.standard_price:
                _logger.warning(f'Skipping shipment {transfer_name} because product {product.name} has no cost set.')
                return
            
            # if we should skip inventory not using AVCO
            if account.skip_inventory_not_avco and product.cost_method != 'average':
                _logger.warning(f'Skipping shipment {transfer_name} because product {product.name} is not using AVCO.')
                return

            delivery_move_vals = {
                'name': f"FBA Inbound {shipment_id} - {msku}",
                'product_id': product.id,
                'product_uom_qty': item_qty,
                'quantity': item_qty,
                'availability': item_qty,
                'product_uom': self.env.ref('uom.product_uom_unit').id,
                'location_id': from_warehouse_location.id,
                'location_dest_id': fba_transit_loc.id,
            }

            reciept_move_vals = {
                'name': f"FBA Inbound {shipment_id} - {msku} (Transit to Inbound)",
                'product_id': product.id,
                'product_uom_qty': item_qty,
                'quantity': item_qty,
                'availability': item_qty,
                'product_uom': self.env.ref('uom.product_uom_unit').id,
                'location_id': fba_transit_loc.id,
                'location_dest_id': fba_inbound_loc.id,
            }

            # Add the moves to the queue
            moves_queue.append((delivery_move_vals, reciept_move_vals))

        if not moves_queue:
            _logger.warning('No valid moves found for FBA inbound shipment %s. Skipping this shipment.', transfer_name)
            return

        # Create the stock picking
        pick = self.env['stock.picking'].create(pick_vals)
        _logger.info('Created internal transfer for FBA inbound shipment %s', transfer_name)

        # Create the stock moves for delivery and receipt
        for delivery_move_vals, reciept_move_vals in moves_queue:
            delivery_move_vals['picking_id'] = pick.id
            reciept_move_vals['picking_id'] = pick.id

            self.env['stock.move'].create(delivery_move_vals)
            self.env['stock.move'].create(reciept_move_vals)

        # Confirm the picking to create the stock moves
        pick.action_confirm()
        _logger.info('Confirmed internal transfer for FBA inbound shipment %s', transfer_name)

        # Assign the stock moves
        pick.action_assign()
        _logger.info('Assigned stock moves for FBA inbound shipment %s', transfer_name)

        # Validate the picking to complete the transfer
        pick.button_validate()
        _logger.info('Validated internal transfer for FBA inbound shipment %s', transfer_name)


    def get_fba_transit_loc(self):
        """
        Get or create the FBA transit location. This location is used to hold FBA inbound shipments before they are transferred to the FBA Inbound location. It is a Partner/Customer location to allow for landed cost transactions.
        """
        fba_partner_loc = self.env['stock.location'].search([('name', '=', 'FBA Transit')], limit=1)
        if not fba_partner_loc:
            fba_partner_loc = self.env['stock.location'].create({
                'name': 'FBA Transit',
                'usage': 'customer',
                'location_id': self.env.ref('stock.stock_location_customers').id,
            })

        return fba_partner_loc


    def check_for_cancelled_fba_inbound_shipment(self, existing_pick, shipment, transfer_name, fba_wh):
        if shipment.get('ShipmentStatus') == 'CANCELLED':

            return_name = f'Cancelled Shipment {transfer_name}'

            # See if we already have a return picking for this shipment
            existing_return_pick = self.env['stock.picking'].search([
                ('origin', '=', return_name),
            ], limit=1)

            if existing_return_pick:
                _logger.info('Return picking for cancelled shipment %s already exists. Skipping creation.', transfer_name)
                return

            # return the shipment
            _logger.info('FBA inbound shipment %s is cancelled. Reverting stock moves.', transfer_name)
            
            # Prepare values for the return picking
            return_picking_vals = {
                'picking_type_id': fba_wh.out_type_id.id,  # Use the outbound picking type of the warehouse
                'location_id': existing_pick.location_dest_id.id,  # Destination of original picking becomes source for return
                'location_dest_id': existing_pick.location_id.id,  # Source of original picking becomes destination for return
                'origin': return_name,
                'partner_id': existing_pick.partner_id.id,
            }

            # Create the return picking
            return_picking = self.env['stock.picking'].create(return_picking_vals)

            # Create return moves for each original move line
            for move_line in existing_pick.move_ids:
                return_move_vals = {
                    'product_id': move_line.product_id.id,
                    'product_uom_qty': move_line.product_uom_qty,
                    'product_uom': move_line.product_uom.id,
                    'location_id': move_line.location_dest_id.id,  # Destination of original move becomes source for return move
                    'location_dest_id': move_line.location_id.id,  # Source of original move becomes destination for return move
                    'picking_id': return_picking.id,
                    'name': 'Return: ' + move_line.product_id.name,
                }
                self.env['stock.move'].create(return_move_vals)

            # Validate the return picking (optional, depending on your workflow)
            return_picking.button_validate()
