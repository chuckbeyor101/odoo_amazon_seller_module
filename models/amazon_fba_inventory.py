
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

from asyncio.log import logger
from datetime import datetime
from datetime import date
import logging
import traceback
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from .utils import amazon_utils
import random

_logger = logging.getLogger(__name__)


class AmazonFBAInventory(models.Model):
    _name = 'amazon.fba.inventory'
    _description = 'Amazon FBA Inventory'
    _auto = False  # Don't create a database table for this model, since it doesn't store data directly

    @api.model
    def cron_fba_inventory_sync(self):
        amz_seller_accounts = self.env['amazon.seller.account'].search([('import_fba_inventory', '=', True)])
        _logger.info('Starting Amazon FBA inventory sync cron job for %s account(s) with FBA import enabled', len(amz_seller_accounts))
        self.get_fba_warehouse() # Initialize FBA warehouse and stock locations
        
        for amz_account in amz_seller_accounts:
            try:
                _logger.info('Importing FBA inventory for account: %s', amz_account.name)
                self._update_account_fba_inventory(amz_account)

            except Exception as e:
                _logger.error('Error importing FBA inventory for account %s: %s', amz_account.name, str(e))
                _logger.error(traceback.format_exc())
                raise ValidationError(f'Failed to import FBA inventory for account {amz_account.name}: {str(e)} \n{traceback.format_exc()}')


    @api.model
    def _update_account_fba_inventory(self, amz_account):
        # Get all products
        product_list = self.env['product.template'].search([])

        if not product_list:
            _logger.warning('No products found for account %s', amz_account.name)
            return
        
        _logger.info('Found %s products for account %s', len(product_list), amz_account.name)

        fba_wh, fba_inbound_loc, fba_stock_loc, fba_reserved_loc, fba_researching_loc, fba_unfulfillable_loc = self.get_fba_warehouse()

        for product in product_list:
            # See if we should skip inventory without cost
            if amz_account.skip_inventory_when_no_product_cost and not product.standard_price:
                _logger.warning('Skipping inventory update for product %s because it has no cost', product.name)
                continue

            # if we should skip inventory not using AVCO
            if amz_account.skip_inventory_not_avco and product.cost_method != 'average':
                _logger.warning('Skipping inventory update for product %s because it is not using AVCO', product.name)
                continue

            # Get FBA inventory for each product by summing each msku's quantities
            amazon_msku_list = product.amazon_msku_ids

            if not amazon_msku_list:
                _logger.debug('No Amazon MSKUs found for product: %s', product.name)
                continue

            total_fulfillable_quantity = 0
            total_inbound_quantity = 0
            total_reserved_quantity = 0
            total_researching_quantity = 0
            total_unfulfillable_quantity = 0
            total_future_supply_quantity = 0

            for amazon_msku in amazon_msku_list:
                fba_inventory = amazon_utils.get_fba_inventory_summary_by_sku(amazon_msku.name, amz_account)

                if not fba_inventory:
                    _logger.debug('No FBA inventory found for MSKU: %s', amazon_msku.name)
                    continue

                total_inbound_quantity += fba_inventory.get('inventoryDetails',{}).get('inboundWorkingQuantity', 0)
                total_inbound_quantity += fba_inventory.get('inventoryDetails',{}).get('inboundShippedQuantity', 0)
                total_inbound_quantity += fba_inventory.get('inventoryDetails',{}).get('inboundReceivingQuantity', 0)

                total_fulfillable_quantity += fba_inventory.get('inventoryDetails',{}).get('fulfillableQuantity', 0)
                total_reserved_quantity += fba_inventory.get('inventoryDetails',{}).get('reservedQuantity', {}).get('totalReservedQuantity', 0)
                total_researching_quantity += fba_inventory.get('inventoryDetails',{}).get('researchingQuantity', {}).get('totalResearchingQuantity', 0)
                total_unfulfillable_quantity += fba_inventory.get('inventoryDetails',{}).get('unfulfillableQuantity', {}).get('totalUnfulfillableQuantity', 0)
                # total_future_supply_quantity += fba_inventory.get('inventoryDetails',{}).get('futureSupplyQuantity', 0)

                date_string = datetime.now().strftime('%Y-%m-%d')
                self.fba_inventory_adjustment(product, fba_inbound_loc, total_inbound_quantity, fba_wh, f"FBA Inventory Sync (Inbound): {amazon_msku.name}, {date_string}")
                self.fba_inventory_adjustment(product, fba_stock_loc, total_fulfillable_quantity, fba_wh, f"FBA Inventory Sync (Stock): {amazon_msku.name}, {date_string}")
                self.fba_inventory_adjustment(product, fba_reserved_loc, total_reserved_quantity, fba_wh, f"FBA Inventory Sync (Reserved): {amazon_msku.name}, {date_string}")
                self.fba_inventory_adjustment(product, fba_researching_loc, total_researching_quantity, fba_wh, f"FBA Inventory Sync (Researching): {amazon_msku.name}, {date_string}")
                self.fba_inventory_adjustment(product, fba_unfulfillable_loc, total_unfulfillable_quantity, fba_wh, f"FBA Inventory Sync (Unfulfillable): {amazon_msku.name}, {date_string}")
                #TODO: Not sure if we should set future supply quantity, or if its already considered in the other quantities


    def fba_inventory_adjustment(self, product, location, final_quantity, fba_wh, name):
        # Get current quantity in the location
        current_qty = self.env['stock.quant']._get_available_quantity(product, location)
        delta_qty = final_quantity - current_qty
        
        inventory_adjustment_location = self.get_fba_inv_adj_location()

        if not inventory_adjustment_location:
            _logger.error('No FBA Inventory Adjustment location found. Cannot perform inventory adjustment for product %s at location %s', product.name, location.name)
            return

        if delta_qty > 0:
            source_location = inventory_adjustment_location
            destination_location = location
        elif delta_qty < 0:
            source_location = location
            destination_location = inventory_adjustment_location
            delta_qty = abs(delta_qty)
        else:
            _logger.debug('No inventory adjustment needed for product %s at location %s', product.name, location.name)
            return
        
        # Add Qty to the name for clarity
        name = f'{name} ({delta_qty}) - {random.randint(1000, 9999)}'
        
        fba_internal_picking_type = self.env['stock.picking.type'].search([('code', '=', 'internal'),('warehouse_id', '=', fba_wh.id),], limit=1)

        picking = self.env['stock.picking'].create({
            'name': name,
            'picking_type_id': fba_internal_picking_type.id,
            'location_id': source_location.id,
            'location_dest_id': destination_location.id,
            'state': 'draft',
        })

        move = self.env['stock.move'].create({
            'name': name,
            'product_id': product.id,
            'product_uom_qty': delta_qty,
            'quantity': delta_qty,
            'availability': delta_qty,
            'product_uom': product.uom_id.id,
            'location_id': source_location.id,
            'location_dest_id': destination_location.id,
            'state': 'draft',
            'picking_id': picking.id,
        })

        # Validate the picking to create the stock quant
        picking.action_confirm()
        picking.action_assign() 
        picking._action_done()
        picking.button_validate()

        _logger.info('Inventory adjustment for product %s at location %s: %s units adjusted', product.name, location.name, delta_qty)


    def get_fba_inv_adj_location(self):
        """
        Ensure the FBA Inventory Adjustment location exists.
        """
        _logger.debug('Ensuring FBA Inventory Adjustment location exists')

        location = self.env['stock.location'].search([
            ('name', '=', 'FBA Inventory adjustment'),
            ('usage', '=', 'inventory'),
        ], limit=1)

        if not location:
            _logger.info('Creating FBA Inventory Adjustment location')
            location = self.env['stock.location'].create({
                'name': 'FBA Inventory adjustment',
                'usage': 'inventory',
                'location_id': self.env.ref('stock.stock_location_stock').id,
            })
        else:
            _logger.debug('Using existing FBA Inventory Adjustment location %s', location.display_name)

        return location


    def get_fba_warehouse(self):
        """
        Ensure the FBA warehouse and necessary stock locations exist.
        """
        _logger.debug('Ensuring FBA warehouse and stock locations exist')

        Warehouse = self.env['stock.warehouse']
        company = self.env.company

        warehouse = Warehouse.search([('code', '=', 'FBA'), ('company_id', '=', company.id)], limit=1)
        if not warehouse:
            _logger.info('Creating FBA warehouse for company %s', company.name)
            warehouse = Warehouse.create({
                'name': 'FBA',
                'code': 'FBA',
                'company_id': company.id,
            })
        else:
            _logger.debug('Using existing FBA warehouse %s', warehouse.display_name)

        # Check for stock location with the name 'Inbound' in the FBA warehouse
        inbound_loc = self.env['stock.location'].search([
            ('name', '=', 'Inbound'),
            ('usage', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id)
        ], limit=1)
        
        if not inbound_loc:
            _logger.info('Creating Inbound stock location in FBA warehouse %s', warehouse.display_name)
            inbound_loc = self.env['stock.location'].create({
                'name': 'Inbound',
                'usage': 'internal',
                'location_id': warehouse.view_location_id.id,
                'warehouse_id': warehouse.id,
            })
            warehouse.wh_input_stock_loc_id = inbound_loc.id
        else:
            _logger.debug('Using existing Inbound stock location %s', inbound_loc.display_name)

        # Check for stock location with the name 'Stock' in the FBA warehouse
        stock_loc = self.env['stock.location'].search([
            ('name', '=', 'Stock'),
            ('usage', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id)
        ], limit=1)

        if not stock_loc:
            _logger.info('Creating Stock stock location in FBA warehouse %s', warehouse.display_name)
            stock_loc = self.env['stock.location'].create({
                'name': 'Stock',
                'usage': 'internal',
                'location_id': warehouse.view_location_id.id,
                'warehouse_id': warehouse.id,
            })
            warehouse.lot_stock_id = stock_loc.id
        else:
            _logger.debug('Using existing Stock stock location %s', stock_loc.display_name)

        # Check for stock location with the name 'Reserved' in the FBA warehouse
        reserved_loc = self.env['stock.location'].search([
            ('name', '=', 'Reserved'),
            ('usage', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id)
        ], limit=1)

        if not reserved_loc:
            _logger.info('Creating Reserved stock location in FBA warehouse %s', warehouse.display_name)
            reserved_loc = self.env['stock.location'].create({
                'name': 'Reserved',
                'usage': 'internal',
                'location_id': warehouse.view_location_id.id,
                'warehouse_id': warehouse.id,
            })
        else:
            _logger.debug('Using existing Reserved stock location %s', reserved_loc.display_name)

        # Check for stock location with the name 'Researching' in the FBA warehouse
        researching_loc = self.env['stock.location'].search([
            ('name', '=', 'Researching'),
            ('usage', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id)
        ], limit=1)

        if not researching_loc:
            _logger.info('Creating Researching stock location in FBA warehouse %s', warehouse.display_name)
            researching_loc = self.env['stock.location'].create({
                'name': 'Researching',
                'usage': 'internal',
                'location_id': warehouse.view_location_id.id,
                'warehouse_id': warehouse.id,
            })
        else:
            _logger.debug('Using existing Researching stock location %s', researching_loc.display_name)

        # Check for stock location with the name 'Unfulfillable' in the FBA warehouse
        unfulfillable_loc = self.env['stock.location'].search([
            ('name', '=', 'Unfulfillable'),
            ('usage', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id)
        ], limit=1)

        if not unfulfillable_loc:
            _logger.info('Creating Unfulfillable stock location in FBA warehouse %s', warehouse.display_name)
            unfulfillable_loc = self.env['stock.location'].create({
                'name': 'Unfulfillable',
                'usage': 'internal',
                'location_id': warehouse.view_location_id.id,
                'warehouse_id': warehouse.id,
            })
        else:
            _logger.debug('Using existing Unfulfillable stock location %s', unfulfillable_loc.display_name)

        return warehouse, inbound_loc, stock_loc, reserved_loc, researching_loc, unfulfillable_loc