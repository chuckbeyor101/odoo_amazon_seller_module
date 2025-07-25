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

class AmazonAWDInventory(models.Model):
    _name = 'amazon.awd.inventory'
    _description = 'Amazon AWD Inventory'
    _auto = False  # Don't create a database table for this model, since it doesn't store data directly

    @api.model
    def cron_awd_inventory_sync(self):
        amz_seller_accounts = self.env['amazon.seller.account'].search([('import_awd_inventory', '=', True)])
        _logger.info('Starting Amazon AWD inventory sync cron job for %s account(s) with AWD import enabled', len(amz_seller_accounts))
        self.get_awd_warehouse()  # Initialize AWD warehouse and stock locations
        for amz_account in amz_seller_accounts:
            try:
                _logger.info('Importing AWD inventory for account: %s', amz_account.name)
                self._update_account_awd_inventory(amz_account)

            except Exception as e:
                _logger.error('Error importing AWD inventory for account %s: %s', amz_account.name, str(e))
                _logger.error(traceback.format_exc())
                raise ValidationError(f'Failed to import AWD inventory for account {amz_account.name}: {str(e)} \n{traceback.format_exc()}')


    @api.model
    def _update_account_awd_inventory(self, amz_account):
        awd_inventory_list = amazon_utils.list_all_awd_inventory(amz_account)

        if not awd_inventory_list:
            _logger.warning('No AWD inventory found for account %s', amz_account.name)
            return
        
        _logger.info('Found %s AWD inventory items for account %s', len(awd_inventory_list), amz_account.name)

        awd_wh, awd_inbound_loc, awd_stock_loc = self.get_awd_warehouse()

        finished_skus = []

        for awd_inventory in awd_inventory_list:
            sku = awd_inventory.get('sku')
            if not sku:
                _logger.warning('AWD inventory item missing SKU: %s', awd_inventory)
                continue
            
            if sku in finished_skus:
                _logger.debug('Skipping already processed SKU: %s', sku)
                continue

            # Find product by SKU
            product = self.env['product.template'].find_by_msku(sku)

            if not product:
                _logger.debug('No product found for SKU: %s', sku)
                continue

            # See if we should skip inventory without cost
            if amz_account.skip_inventory_when_no_product_cost and not product.standard_price:
                _logger.warning('Skipping inventory update for product %s because it has no cost', product.name)
                continue

            # Get all Amazon mskus for the product to account for the sum of quantities
            amazon_msku_list = product.amazon_msku_ids

            total_product_inbound_quantity = 0
            total_product_on_hand_quantity = 0

            for amazon_msku in amazon_msku_list:    
                # Find the matching AWD inventory item for this msku
                matching_awd_inventory = next((item for item in awd_inventory_list if item.get('sku') == amazon_msku.name), None)
                if matching_awd_inventory:
                    total_product_inbound_quantity += matching_awd_inventory.get('totalInboundQuantity', 0)
                    total_product_on_hand_quantity += matching_awd_inventory.get('totalOnhandQuantity', 0)

                # Update the finished SKUs list
                finished_skus.append(amazon_msku.name)

            # Adjust the inventory in Odoo
            self.env['stock.quant'].set_available_quantity(product, awd_inbound_loc, total_product_inbound_quantity, "AWD Inventory Sync (Inbound):")
            self.env['stock.quant'].set_available_quantity(product, awd_stock_loc, total_product_on_hand_quantity, "AWD Inventory Sync (Stock):")

        
    def get_awd_warehouse(self):
        """
        Ensure the AWD warehouse and necessary stock locations exist.
        """
        _logger.debug('Ensuring AWD warehouse and stock locations exist')

        Warehouse = self.env['stock.warehouse']
        company = self.env.company

        warehouse = Warehouse.search([('code', '=', 'AWD'), ('company_id', '=', company.id)], limit=1)
        if not warehouse:
            _logger.info('Creating AWD warehouse for company %s', company.name)
            warehouse = Warehouse.create({
                'name': 'AWD',
                'code': 'AWD',
                'company_id': company.id,
            })
        else:
            _logger.debug('Using existing AWD warehouse %s', warehouse.display_name)

        # Check for stock location with the name 'Inbound' in the AWD warehouse
        inbound_loc = self.env['stock.location'].search([
            ('name', '=', 'Inbound'),
            ('usage', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id)
        ], limit=1)
        
        if not inbound_loc:
            _logger.info('Creating Inbound stock location in AWD warehouse %s', warehouse.display_name)
            inbound_loc = self.env['stock.location'].create({
                'name': 'Inbound',
                'usage': 'internal',
                'location_id': warehouse.view_location_id.id,
                'warehouse_id': warehouse.id,
            })
            warehouse.wh_input_stock_loc_id = inbound_loc.id
        else:
            _logger.debug('Using existing Inbound stock location %s', inbound_loc.display_name)

        # Check for stock location with the name 'Stock' in the AWD warehouse
        stock_loc = self.env['stock.location'].search([
            ('name', '=', 'Stock'),
            ('usage', '=', 'internal'),
            ('warehouse_id', '=', warehouse.id)
        ], limit=1)

        if not stock_loc:
            _logger.info('Creating Stock stock location in AWD warehouse %s', warehouse.display_name)
            stock_loc = self.env['stock.location'].create({
                'name': 'Stock',
                'usage': 'internal',
                'location_id': warehouse.view_location_id.id,
                'warehouse_id': warehouse.id,
            })
            warehouse.lot_stock_id = stock_loc.id
        else:
            _logger.debug('Using existing Stock stock location %s', stock_loc.display_name)

        return warehouse, inbound_loc, stock_loc