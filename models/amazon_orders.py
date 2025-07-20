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

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    amazon_seller_order_id = fields.Char(
        string='Amazon Seller Order ID',
        help='Amazon order identifier from the seller central',
        index=True
    )

class AmazonOrders(models.Model):
    _name = 'amazon.orders'
    _description = 'Amazon Orders'
    _auto = False  # Don't create a database table for this model, since it doesn't store data directly

    def get_fba_partner(self):
        """
        Get the FBA partner for the current environment.
        """
        Partner = self.env['res.partner']
        fba_partner = Partner.search([('name', '=', 'Amazon_FBA')], limit=1)
        
        if not fba_partner:
            _logger.info('Creating FBA partner')
            fba_partner = Partner.create({
                'name': 'Amazon_FBA',
                'is_company': True,
                'company_type': 'company',
            })
        else:
            _logger.debug('Using existing FBA partner %s', fba_partner.display_name)

        return fba_partner

    def get_or_create_shipping_partner(self, partner, type, name=None, address1=None, address2=None, city=None, state=None, zip_code=None, country_code=None):
        """
        Get or create a shipping partner for the given address.
        """
        Partner = self.env['res.partner']
        
        shipping_partner = Partner.search([
            ('type', '=', type),
            ('name', '=', name),
            ('street', '=', address1),
            ('street2', '=', address2 or ''),
            ('city', '=', city or ''),
            ('state_id.code', '=', state or ''),
            ('zip', '=', zip_code or ''),
            ('country_id.code', '=', country_code),
            ('parent_id', '=', partner.id)
        ], limit=1)

        if not shipping_partner:
            _logger.info('Creating shipping partner for %s', partner.name)
            shipping_partner = Partner.create({
                'type': type,
                'name': name,
                'street': address1,
                'street2': address2 or '',
                'city': city or '',
                'state_id': self.env['res.country.state'].search([('code', '=', state)], limit=1).id if state else False,
                'zip': zip_code or '',
                'country_id': self.env['res.country'].search([('code', '=', country_code)], limit=1).id,
                'parent_id': partner.id,
            })
        else:
            _logger.debug('Using existing shipping partner %s', shipping_partner.display_name)

        return shipping_partner

    def get_fba_medium(self):
        """
        Get the FBA medium for the current environment.
        """
        fba_medium = self.env['utm.medium'].search([('name', '=', 'Amazon FBA')], limit=1)
        if not fba_medium:
            _logger.debug('Creating FBA medium')
            fba_medium = self.env['utm.medium'].create({
                'name': 'Amazon FBA'
            })

        return fba_medium

    def get_fba_source(self):
        """
        Get the FBA source for the current environment.
        """
        fba_source = self.env['utm.source'].search([('name', '=', 'Amazon FBA')], limit=1)
        if not fba_source:
            _logger.debug('Creating FBA source')
            fba_source = self.env['utm.source'].create({
                'name': 'Amazon FBA'
            })

        return fba_source

    def get_fba_tag(self):
        """
        Get the FBA CRM tag for the current environment.
        """
        fba_tag = self.env['crm.tag'].search([('name', '=', 'Amazon FBA')], limit=1)
        if not fba_tag:
            _logger.debug('Creating FBA CRM tag')
            fba_tag = self.env['crm.tag'].create({
                'name': 'Amazon FBA'
            })

        return fba_tag

    def get_fbm_medium(self):
        """
        Get the FBM medium for the current environment.
        """
        fbm_medium = self.env['utm.medium'].search([('name', '=', 'Amazon FBM')], limit=1)
        if not fbm_medium:
            _logger.debug('Creating FBM medium')
            fbm_medium = self.env['utm.medium'].create({
                'name': 'Amazon FBM'
            })

        return fbm_medium

    def get_fbm_source(self):
        """
        Get the FBM source for the current environment.
        """
        fbm_source = self.env['utm.source'].search([('name', '=', 'Amazon FBM')], limit=1)
        if not fbm_source:
            _logger.debug('Creating FBM source')
            fbm_source = self.env['utm.source'].create({
                'name': 'Amazon FBM'
            })

        return fbm_source

    def get_fbm_tag(self):
        """
        Get the FBM CRM tag for the current environment.
        """
        fbm_tag = self.env['crm.tag'].search([('name', '=', 'Amazon FBM')], limit=1)
        if not fbm_tag:
            _logger.debug('Creating FBM CRM tag')
            fbm_tag = self.env['crm.tag'].create({
                'name': 'Amazon FBM'
            })

        return fbm_tag

    @api.model
    def cron_import_orders(self):
        """
        Import orders from Amazon.
        """

        # accounts with either FBA or FBM order import enabled
        accounts = self.env['amazon.seller.account'].search([
            '|',
            ('import_fba_orders', '=', True),
            ('import_fbm_orders', '=', True)
        ])
        _logger.info('Starting Amazon orders import cron job for %s account(s)', len(accounts))
        for account in accounts:
            try:
                _logger.info('Importing Amazon orders for account: %s', account.name)

                # Import orders for the account
                self.import_account_orders(account)

                # Ensure all FBA orders are marked as shipped
                self.ensure_fba_orders_shipped(account)

                # if invoice_fba_orders is enabled, ensure all FBA orders are invoiced
                if account.invoice_fba_orders:
                    self.ensure_fba_orders_invoiced(account)


            except Exception as e:
                _logger.error('Error importing Amazon orders for account %s: %s', account.name, str(e))
                _logger.error(traceback.format_exc())
                raise ValidationError(f'Failed to import Amazon orders for account {account.name}: {str(e)} \n{traceback.format_exc()}')
            
    @api.model
    def ensure_fba_orders_shipped(self, account):
        """
        Ensure that all orders are marked as shipped if they are FBA orders.
        This is to ensure that the FBA orders are processed correctly.
        """
        _logger.info('Ensuring all FBA orders are marked as shipped for account: %s', account.name)

        fba_tag = self.get_fbm_tag()

        fba_orders = self.env['sale.order'].search([
            ('tag_ids', 'in', fba_tag.id),
        ])

        fba_inventory_model = self.env['amazon.fba.inventory']
        warehouse, inbound_loc, stock_loc, reserved_loc, researching_loc, unfulfillable_loc = fba_inventory_model.get_fba_warehouse()

        for order in fba_orders:
            if order.state in ['sale', 'done']:
                self.ship_order(order, warehouse)


    @api.model
    def ensure_fba_orders_invoiced(self, account):
        """
        Ensure that all FBA orders are invoiced if the invoice_fba_orders setting is enabled.
        This is to ensure that the FBA orders are processed correctly.
        """
        _logger.info('Ensuring all FBA orders are invoiced for account: %s', account.name)

        fba_tag = self.get_fba_tag()

        fba_orders = self.env['sale.order'].search([
            ('tag_ids', 'in', fba_tag.id),
            ('state', '=', 'sale'),
            ('invoice_status', '!=', 'invoiced')
        ])

        for order in fba_orders:
            if order.invoice_status != 'invoiced':
                self.invoice_order(order, account)

    @api.model
    def import_account_orders(self, account):
        """
        Import Amazon orders for a specific account.
        """
        amz_orders = amazon_utils.get_orders_recently_updated(account, days=5)

        if not amz_orders:
            _logger.info('No recently updated Amazon orders found for account: %s', account.name)
            return

        _logger.info('Found %s recently updated Amazon orders for account: %s', len(amz_orders), account.name)

        updated_count = 0
        created_count = 0

        for amz_order in amz_orders:
            try:
                # Check for existing order
                existing_order = self.env['sale.order'].search([
                    ('amazon_seller_order_id', '=', amz_order.get('AmazonOrderId'))
                    ], limit=1)

                if existing_order: 
                    _logger.debug('Updating existing Amazon order: %s', existing_order.name)
                    if amz_order.get('FulfillmentChannel') == 'AFN' and account.import_fba_orders:
                        self.update_order(amz_order, account, "FBA")
                        updated_count += 1
                    
                    elif amz_order.get('FulfillmentChannel') == 'MFN' and account.import_fbm_orders:
                        self.update_order(amz_order, account, "FBM")
                        updated_count += 1

                else:
                    _logger.debug('Creating new Amazon order for Amazon Order ID: %s', amz_order.get('AmazonOrderId'))
                    if amz_order.get('FulfillmentChannel') == 'AFN' and account.import_fba_orders:
                        if amz_order.get('OrderStatus') in ['Shipped']:
                            self.create_order(amz_order, account, "FBA")
                            created_count += 1

                    elif amz_order.get('FulfillmentChannel') == 'MFN' and account.import_fbm_orders:
                        # TODO: Handle FBM orders
                        _logger.error('FBM fulfillment type is not yet implemented for Amazon Order ID: %s', amz_order.get('AmazonOrderId'))
                        #self.create_order(amz_order, account, "FBM")
                        # created_count += 1

            except Exception as e:
                _logger.error('Error processing Amazon order %s: %s', amz_order.get('AmazonOrderId'), str(e))
                _logger.error(traceback.format_exc())
                raise ValidationError(f'Failed to process Amazon order {amz_order.get("AmazonOrderId")}: {str(e)} \n{traceback.format_exc()}')


    @api.model
    def create_order(self, amz_order, account, fulfillment_type):
        """
        Create a new Amazon order.
        """
        _logger.debug('Creating order for Amazon Order ID: %s', amz_order.get('AmazonOrderId'))

        amz_order_items = amazon_utils.get_order_items(account, amz_order.get('AmazonOrderId'))
        if not amz_order_items:
            _logger.warning('No order items found for Amazon Order ID: %s', amz_order.get('AmazonOrderId'))
            return
        
        
        if fulfillment_type == "FBA":
            fba_inventory_model = self.env['amazon.fba.inventory']
            warehouse, inbound_loc, stock_loc, reserved_loc, researching_loc, unfulfillable_loc = fba_inventory_model.get_fba_warehouse()
            medium = self.get_fba_medium()
            source = self.get_fba_source()
            tag = self.get_fba_tag()
            if account.consolidated_fba_order_customer:
                partner = self.get_fba_partner()
                shipping_partner = self.get_or_create_shipping_partner(
                    partner=partner, 
                    type="delivery", 
                    name="Amazon FBA", 
                    city=amz_order.get('ShippingAddress', {}).get('City', ''),
                    state=amz_order.get('ShippingAddress', {}).get('StateOrRegion', ''),
                    zip_code=amz_order.get('ShippingAddress', {}).get('PostalCode', ''), 
                    country_code=amz_order.get('ShippingAddress', {}).get('CountryCode', ''),
                    )
                _logger.debug(f"Created or found shipping partner for FBA order: {shipping_partner.id} {shipping_partner.city}")
            else:
                # TODO: Handle non-consolidated FBA orders
                _logger.error('Non-consolidated FBA orders are not yet implemented.')
                return
        else:
            # TODO : Handle FBM warehouse logic
            _logger.error('FBM fulfillment type is not yet implemented.')
            medium = self.get_fbm_medium()
            source = self.get_fbm_source()
            tag = self.get_fbm_tag()
            return
        

        # Create the sale order
        order_vals = {
            'partner_id': partner.id,
            'amazon_seller_order_id': amz_order.get('AmazonOrderId'),
            'origin': amz_order.get('AmazonOrderId'),
            'warehouse_id': warehouse.id,
            'source_id': source.id,
            'medium_id': medium.id,
            'tag_ids': [(6, 0, [tag.id])],
            'partner_shipping_id': shipping_partner.id,
        }

        order = self.env['sale.order'].create(order_vals)

        # Create order lines
        for item in amz_order_items:

            product = self.env['product.product'].search([('amazon_asin', '=', item.get('ASIN'))], limit=1)
            if not product:
                _logger.warning('Product not found for SKU: %s', item.get('SellerSKU'))
                return

            # Determine item price.
            line_price = float(item.get('ItemPrice', {}).get('Amount', 0.0))
            line_qty = int(item.get('QuantityOrdered', 1))
            if line_qty <= 0:
                _logger.warning('Invalid quantity for item %s in order %s: %s', item.get('SellerSKU'), amz_order.get('AmazonOrderId'), line_qty)
                continue
            if line_price <= 0:
                unit_price = 0.0
            else:
                unit_price = line_price / line_qty

            order_line_vals = {
                'order_id': order.id,
                'product_id': product.id,
                'product_uom_qty': item.get('QuantityOrdered'),
                'price_unit': unit_price,
                'name': product.name,
                'discount': float(item.get('PromotionalDiscount', {}).get('Amount', 0.0)),
            }

            # Get or create a tax profile for the lines tax percent if import_order_tax is enabled
            if account.import_fba_order_tax:
                line_tax = float(item.get('ItemTax', {}).get('Amount', 0.0)) + float(item.get('PromotionalDiscountTax', {}).get('Amount', 0.0))
                line_price = float(item.get('ItemPrice', {}).get('Amount', 0.0)) + float(item.get('PromotionalDiscount', {}).get('Amount', 0.0))
                tax_profile = self.get_or_create_tax_profile_by_price_calculation(line_price, line_tax)
                if tax_profile:
                    order_line_vals['tax_id'] = [(6, 0, [tax_profile.id])]
            
            self.env['sale.order.line'].create(order_line_vals)

            # Handle shipping cost if available
            if account.import_fba_order_shipping and "ShippingPrice" in item:
                shipping_cost_product = amazon_utils.get_or_create_shipping_cost_product(self.env, account)
                # Determine shipping tax
                shipping_tax = float(item.get('ShippingTax', {}).get('Amount', 0.0)) + float(item.get('ShippingDiscountTax', {}).get('Amount', 0.0))
                shipping_price = float(item.get('ShippingPrice', {}).get('Amount', 0.0)) - float(item.get('ShippingDiscount', {}).get('Amount', 0.0))
                shipping_tax_profile = self.get_or_create_tax_profile_by_price_calculation(shipping_price, shipping_tax)

                shipping_line_vals = {
                    'order_id': order.id,
                    'product_id': shipping_cost_product.id,
                    'product_uom_qty': 1,  # Assuming shipping cost is per order
                    'price_unit': shipping_price,
                    'name': shipping_cost_product.name,
                    'discount': float(item.get('ShippingDiscount', {}).get('Amount', 0.0)),
                }

                if shipping_tax_profile:
                    shipping_line_vals['tax_id'] = [(6, 0, [shipping_tax_profile.id])]

                self.env['sale.order.line'].create(shipping_line_vals)


        _logger.debug('Created order for Amazon Order ID: %s with %s lines', amz_order.get('AmazonOrderId'), len(order.order_line))

        # Confirm the order
        order.action_confirm()
        _logger.debug('Confirmed order for Amazon Order ID: %s', amz_order.get('AmazonOrderId'))

        # If fulfillment type is FBA, create the delivery picking
        if fulfillment_type == "FBA":
            self.ship_order(order, warehouse)

        # Reset order dates
        order_date = datetime.strptime(amz_order.get('PurchaseDate'), '%Y-%m-%dT%H:%M:%SZ')
        shipped_date = order_date + timedelta(days=1)  # Assuming shipped date is next day for simplicity
        commitment_date = datetime.strptime(amz_order.get('LatestShipDate'), '%Y-%m-%dT%H:%M:%SZ')
        order.write({
            'date_order': order_date,
            'write_date': order_date,
            'effective_date': shipped_date,
            'commitment_date': commitment_date,
        })        

        # If account is set to invoice FBA orders, create an invoice
        if account.invoice_fba_orders:
            self.invoice_order(order, account)

    @api.model
    def invoice_order(self, order, account):
        """
        Create an invoice for the given order.
        """
        _logger.debug('Creating invoice for order: %s', order.name)

        # Check if the order is already invoiced
        if order.invoice_status == 'invoiced':
            _logger.info('Order %s is already fully invoiced', order.name)
            return

        # Create the invoice
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': order.partner_id.id,
            'date': order.effective_date or order.date_order,
            'invoice_date': order.effective_date or order.date_order,
            'invoice_origin': order.name,
            'ref': order.name,
            'invoice_line_ids': [(0, 0, {
                'name': line.name,
                'quantity': line.product_uom_qty,
                'price_unit': line.price_unit,
                'tax_ids': [(6, 0, line.tax_id.ids)],
                'product_id': line.product_id.id,
            }) for line in order.order_line],
        })

        # Post the invoice
        invoice.action_post()
        _logger.info('Created invoice %s for order %s', invoice.name, order.name)        

    @api.model
    def ship_order(self, order, warehouse):
        """
        Ship the order by creating a delivery picking.
        """
        _logger.debug('Shipping order for Amazon Order ID: %s', order.amazon_seller_order_id)

        # Get the delivery (picking) for this order based on the order name
        delivery_picking = self.env['stock.picking'].search([
            ('origin', '=', order.name),
            ('picking_type_id', '=', warehouse.out_type_id.id)
        ], limit=1)

        if not delivery_picking:
            _logger.warning('No delivery picking found for order: %s', order.name)
            return
        
        for picking in delivery_picking:

            # Reserve stock for the order
            for line in order.order_line:
                for move in picking.move_ids:
                    if move.product_id.id == line.product_id.id:
                        move.quantity = line.product_uom_qty
                        move.availability = line.product_uom_qty

            # Confirm and assign if necessary
            if picking.state == 'draft':
                picking.action_confirm()

            if picking.state != 'assigned':
                picking.action_assign()

            # Validate shipment (mark as shipped)
            picking.button_validate()


    @api.model
    def update_order(self, amz_order, account, fulfillment_type):
        """
        Update an existing Amazon order.
        """
        _logger.debug('Updating order for Amazon Order ID: %s', amz_order.get('AmazonOrderId'))
        # TODO: Implement the update logic here


    @api.model
    def get_or_create_tax_profile_by_price_calculation(self, price: float, tax: float):
        """
        Get or create a tax profile based on the price and tax amount.
        """
        if price <= 0 or tax <= 0:
            _logger.warning('Invalid price or tax amount for tax profile creation: price=%s, tax=%s', price, tax)
            return None

        tax_percent = (tax / price) * 100
        return self.get_or_create_tax_profile_by_percent(tax_percent)

    
    @api.model
    def get_or_create_tax_profile_by_percent(self, tax_percent:float):
        """
        Get or create a tax profile for the given tax percent.
        """
        # Search or create a tax record for this percentage
        tax_profile_name = f'{tax_percent}%'

        tax = self.env['account.tax'].search([
            ('name', '=', tax_profile_name),
            ('amount', '=', tax_percent),
            ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', 'percent')
        ], limit=1)

        if not tax:
            tax = self.env['account.tax'].create({
                'name': tax_profile_name,
                'amount': tax_percent,
                'amount_type': 'percent',
                'type_tax_use': 'sale',
            })

            _logger.debug('Created new tax profile: %s with percent: %s', tax.name, tax_percent)

        return tax