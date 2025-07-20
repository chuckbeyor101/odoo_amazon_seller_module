
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


class AmazonFBAInventory(models.Model):
    _name = 'amazon.fba.inventory'
    _description = 'Amazon FBA Inventory'
    _auto = False  # Don't create a database table for this model, since it doesn't store data directly

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

    @api.model
    def cron_fba_inventory_sync(self):
        amz_seller_accounts = self.env['amazon.seller.account'].search([('import_fba_inventory', '=', True)])
        _logger.info('Starting Amazon FBA inventory sync cron job for %s account(s) with FBA import enabled', len(amz_seller_accounts))
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

            # Adjust the inventory in Odoo
            self.env['stock.quant'].set_available_quantity(product, fba_inbound_loc, total_inbound_quantity, "FBA Inventory Sync (Inbound):")
            self.env['stock.quant'].set_available_quantity(product, fba_stock_loc, total_fulfillable_quantity, "FBA Inventory Sync (Stock):")
            self.env['stock.quant'].set_available_quantity(product, fba_reserved_loc, total_reserved_quantity, "FBA Inventory Sync (Reserved):")
            self.env['stock.quant'].set_available_quantity(product, fba_researching_loc, total_researching_quantity, "FBA Inventory Sync (Researching):")
            self.env['stock.quant'].set_available_quantity(product, fba_unfulfillable_loc, total_unfulfillable_quantity, "FBA Inventory Sync (Unfulfillable):")

            #TODO: Not sure if we should set future supply quantity, or if its already considered in the other quantities