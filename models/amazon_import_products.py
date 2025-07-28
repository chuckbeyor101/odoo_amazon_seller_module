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

class AmazonMsku(models.Model):
    _name = 'amazon.msku'
    _description = 'Amazon Merchant SKU'
    _rec_name = 'name'
    
    name = fields.Char(string='MSKU', required=True, index=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product', index=True, ondelete='cascade')
    
    _sql_constraints = [
        ('unique_msku_product', 'unique(name, product_tmpl_id)', 'This MSKU already exists for this product!')
    ]

class AmazonFnsku(models.Model):
    _name = 'amazon.fnsku'
    _description = 'Amazon Fulfillment Network SKU'
    _rec_name = 'name'
    
    name = fields.Char(string='FNSKU', required=True, index=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product', index=True, ondelete='cascade')
    
    _sql_constraints = [
        ('unique_fnsku_product', 'unique(name, product_tmpl_id)', 'This FNSKU already exists for this product!')
    ]

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Amazon Fields
    amazon_asin = fields.Char(string='ASIN', required=False, help='Amazon Standard Identification Number', index=True)
    amazon_msku_ids = fields.One2many('amazon.msku', 'product_tmpl_id', string='MSKUs')
    amazon_fnsku_ids = fields.One2many('amazon.fnsku', 'product_tmpl_id', string='FNSKUs')
    
    # Computed display fields for easy viewing
    amazon_msku_display = fields.Char(string='MSKU List', compute='_compute_sku_display', store=True)
    amazon_fnsku_display = fields.Char(string='FNSKU List', compute='_compute_sku_display', store=True)
    
    @api.depends('amazon_msku_ids.name', 'amazon_fnsku_ids.name')
    def _compute_sku_display(self):
        for record in self:
            record.amazon_msku_display = ', '.join(record.amazon_msku_ids.mapped('name'))
            record.amazon_fnsku_display = ', '.join(record.amazon_fnsku_ids.mapped('name'))
    
    def add_msku(self, msku):
        """Add MSKU if not already present"""
        if not msku:
            return
        
        existing = self.amazon_msku_ids.filtered(lambda x: x.name == msku)
        if not existing:
            self.env['amazon.msku'].create({
                'name': msku,
                'product_tmpl_id': self.id
            })
    
    def add_fnsku(self, fnsku):
        """Add FNSKU if not already present"""
        if not fnsku:
            return
        
        existing = self.amazon_fnsku_ids.filtered(lambda x: x.name == fnsku)
        if not existing:
            self.env['amazon.fnsku'].create({
                'name': fnsku,
                'product_tmpl_id': self.id
            })
    
    def has_msku(self, msku):
        """Check if product has a specific MSKU"""
        return bool(self.amazon_msku_ids.filtered(lambda x: x.name == msku))
    
    def has_fnsku(self, fnsku):
        """Check if product has a specific FNSKU"""
        return bool(self.amazon_fnsku_ids.filtered(lambda x: x.name == fnsku))
    
    @api.model
    def find_by_msku(self, msku):
        """Find product by any MSKU - simple and direct"""
        msku_record = self.env['amazon.msku'].search([('name', '=', msku)], limit=1)
        product_id = msku_record.product_tmpl_id.id if msku_record else False
        if not product_id:
            _logger.warning('No product found for MSKU: %s', msku)
            return self.env['product.template']

        return self.env['product.template'].browse(product_id)
    
    @api.model
    def search_by_msku(self, msku, exact_match=False):
        """Search for products by MSKU
        
        Args:
            msku (str): The MSKU to search for
            exact_match (bool): If True, use exact matching (=), otherwise fuzzy matching (ilike)
        
        Returns:
            product.template recordset: Products matching the MSKU
        """
        operator = '=' if exact_match else 'ilike'
        msku_records = self.env['amazon.msku'].search([('name', operator, msku)])
        product_id = msku_records.mapped('product_tmpl_id.id')
        if not product_id:
            _logger.warning('No products found for MSKU: %s', msku)
            return self.env['product.template']
        
        return self.env['product.template'].browse(product_id)
    
    @api.model
    def search_by_fnsku(self, fnsku, exact_match=False):
        """Search for products by FNSKU
        
        Args:
            fnsku (str): The FNSKU to search for
            exact_match (bool): If True, use exact matching (=), otherwise fuzzy matching (ilike)
        
        Returns:
            product.template recordset: Products matching the FNSKU
        """
        operator = '=' if exact_match else 'ilike'
        fnsku_records = self.env['amazon.fnsku'].search([('name', operator, fnsku)])
        return fnsku_records.mapped('product_tmpl_id')

class AmazonImportProducts(models.Model):
    _name = 'amazon.import.products'
    _description = 'Amazon Import Products Helper'
    _auto = False  # Don't create a database table for this model, since it doesn't store data directly

    @api.model
    def cron_import_products(self):
        """
        Import products from Amazon using the provided marketplace and credentials.
        """
        accounts = self.env['amazon.seller.account'].search([('import_products', '=', True)])
        _logger.info('Starting Amazon product import cron job for %s account(s)', len(accounts))
        for account in accounts:
            try:
                _logger.debug('Importing products for account: %s', account.name)
                self.import_account_products(account)

                _logger.debug('Updating product details for account: %s', account.name)
                self.update_product_details(account)

            except Exception as e:
                _logger.error('Error importing products for account %s: %s', account.name, str(e))
                _logger.error(traceback.format_exc())
                raise ValidationError(f'Failed to import products for account {account.name}: {str(e)} \n{traceback.format_exc()}')


    @api.model
    def import_account_products(self, account):
        """
        Import products for a specific Amazon seller account.
        """
        amz_listings = amazon_utils.get_open_listings(account)

        if not amz_listings:
            _logger.debug('No products found for account: %s', account.name)
            return
        
        ProductTemplate = self.env['product.template']
        
        # Process the products as needed, e.g., create or update records
        for amz_listing in amz_listings:
            asin = amz_listing.get('asin')
            msku = amz_listing.get('sku')
            if not asin or not msku:
                continue

            vals = {
                'name': "Unknown",  # Use ASIN as the product name until further details are fetched
                'type': 'consu',  # 'consu' for Goods (tangible products)
                'amazon_asin': asin,
                'is_storable': True,  # Ensure new products track inventory only by quantity.
            }

            # If account is set to update pricing 
            if account.import_product_price and amz_listing.get('price'):
                vals['list_price'] = amz_listing.get('price')
                # TODO Get Business Pricing since it is available in the report

            existing_product = ProductTemplate.search([('amazon_asin', '=', asin)], limit=1)

            if existing_product:
                # Update existing product
                existing_product.write(vals)
                # Add MSKU if not already present
                existing_product.add_msku(msku)
                _logger.debug('Updated existing product: %s', asin)
            else:
                # Create new product
                new_product = ProductTemplate.create(vals)
                # Add MSKU to new product
                new_product.add_msku(msku)
                _logger.info('Created new product: %s', asin)

    @api.model
    def update_product_details(self, account):
        # Get products where the title has not been fetched yet
        products = self.env['product.template'].search([('amazon_asin', '!=', False),])
        #products = self.env['product.template'].search([('name', '=', 'Unknown')])

        for product in products:
            catalog_data = amazon_utils.get_catalog_item(account, product.amazon_asin)
            
            vals = {
                'name': catalog_data.get('summaries', [])[0].get('itemName') if catalog_data.get('summaries') and len(catalog_data.get('summaries')) > 0 else 'Unknown',
            }

            # Determine, and convert weight
            weight = catalog_data.get('attributes', {}).get('item_weight', [{}])[0].get('value')
            weight_units = catalog_data.get('attributes', {}).get('item_weight', [{}])[0].get('unit')
            if weight and weight_units:
                if weight_units == 'pounds':
                    vals['weight'] = weight * 0.453592  # Convert pounds to kg
                elif weight_units == 'ounces':
                    vals['weight'] = weight * 0.0283495  # Convert ounces to kg
                elif weight_units == 'grams':
                    vals['weight'] = weight / 1000.0  # Convert grams to kg
                elif weight_units == 'kilograms':
                    vals['weight'] = weight
                else:
                    _logger.warning('Unknown weight unit %s for ASIN %s', weight_units, product.amazon_asin)

            # determine volume from item package dimensions in meters cubed
            length = catalog_data.get('attributes', {}).get('item_package_dimensions', [{}])[0].get('length', {}).get('value')
            length_units = catalog_data.get('attributes', {}).get('item_package_dimensions', [{}])[0].get('length', {}).get('unit')
            width = catalog_data.get('attributes', {}).get('item_package_dimensions', [{}])[0].get('width', {}).get('value')
            width_units = catalog_data.get('attributes', {}).get('item_package_dimensions', [{}])[0].get('width', {}).get('unit')
            height = catalog_data.get('attributes', {}).get('item_package_dimensions', [{}])[0].get('height', {}).get('value')
            height_units = catalog_data.get('attributes', {}).get('item_package_dimensions', [{}])[0].get('height', {}).get('unit')

            if length and width and height and length_units and width_units and height_units:
                if length_units == 'inches':
                    vals['volume'] = (length * 0.0254) * (width * 0.0254) * (height * 0.0254)
                elif length_units == 'centimeters':
                    vals['volume'] = (length / 100.0) * (width / 100.0) * (height / 100.0)
                elif length_units == 'millimeters': 
                    vals['volume'] = (length / 1000.0) * (width / 1000.0) * (height / 1000.0)
                elif length_units == 'meters':
                    vals['volume'] = length * width * height
                else:
                    _logger.warning('Unknown length unit %s for ASIN %s', length_units, product.amazon_asin)

                # if volume is less than 0.01 but not 0 set to 0.01 since the minimum rounding on odoo is 0.01
                if vals.get('volume', 0) < 0.01 and vals.get('volume', 0) > 0:
                    vals['volume'] = 0.01

            product.write(vals)
            _logger.debug('Updated product details for ASIN: %s', product.amazon_asin)








