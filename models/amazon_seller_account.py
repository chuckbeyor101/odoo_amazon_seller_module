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

import subprocess
import sys
import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

from .utils import amazon_utils

# Token caches are imported so they can be cleared before verifying
# connection details. This prevents a cached token from succeeding
# when a user has updated the credentials with invalid values.

logger = logging.getLogger(__name__)

try:
    from sp_api.api import Sellers
    from sp_api.base import Marketplaces, SellingApiException
    from sp_api.auth.access_token_client import cache as sp_api_token_cache, grantless_cache as sp_api_grantless_cache
except Exception:
    Sellers = None
    Marketplaces = None
    SellingApiException = Exception
    sp_api_token_cache = None
    sp_api_grantless_cache = None


class AmazonSellerAccount(models.Model):
    """Model storing Amazon credentials for a single seller account."""

    _name = 'amazon.seller.account'
    _description = 'Amazon Seller Account'

    name = fields.Char(string='Account Name', required=True)
    app_id = fields.Char(string='App ID', required=True)
    client_secret = fields.Char(string='Client Secret', required=True)
    refresh_token = fields.Char(string='Refresh Token', required=True)
    seller_id = fields.Char(string='Seller ID', required=True)

    marketplace = fields.Selection([
        ('US', 'United States'),
        ('CA', 'Canada'),
        ('MX', 'Mexico'),
    ], string='Marketplace', required=True, default='US')

    # Product Listing Settings
    import_products = fields.Boolean(
        string='Import Products',
        default=False,
        help='Enable automatic import of FBA products from Amazon. This will get your open listings from Amazon and create or update products in Odoo. To update existing products you must have the Amazon ASIN set on the product template, otherwise a new product will be created.'
    )

    import_product_price = fields.Boolean(
        string='Import Product Price',
        default=False,
        help='Enable automatic update of product prices from Amazon. This will update the product prices in Odoo based on the latest data from Amazon. You must have product importing enabled for this to work.'
    )

    # FBA Inventory Settings
    import_fba_inventory = fields.Boolean(
        string='Import FBA Inventory',
        default=False,
        help='Enable automatic import of FBA inventory from Amazon. This will create an FBA warehouse and locations in Odoo, and import the FBA inventory quantities for each product.'
    )

    import_fba_inbound_shipments = fields.Boolean(
        string='Import FBA Inbound Shipments',
        default=False,
        help='Enable automatic import of FBA inbound shipments from Amazon. The origin location of the shipments will be added to the address mapping table. Once mapped the shipments will deduct inventory from the warehouse locations you specified in the address mapping.'
    )

    import_fba_orders = fields.Boolean(
        string='Import FBA Orders',
        default=False,
        help='Enable automatic import of FBA orders from Amazon. This will create sales orders in Odoo for each FBA order.'
    )

    consolidated_fba_order_customer = fields.Boolean(
        string='Consolidated FBA Order Customer',
        default=True,
        help='If enabled, all FBA orders will be assigned to a single customer (Amazon-FBA).'
    )

    import_fba_order_tax = fields.Boolean(
        string='Import FBA Order Tax',
        default=False,
        help='Enable automatic import of order tax from Amazon. This will estimate the tax percentage based on the order total and the tax amount. Then a custom tax profile will be created in Odoo with the estimated tax percentage. This allows you to track taxes that are not set up in Odoo, but are applied to Amazon orders.'
    )

    import_fba_order_shipping = fields.Boolean(
        string='Import FBA Order Shipping',
        default=False,
        help='Enable automatic import of order shipping from Amazon. This will create line items for shipping costs in the sales orders created from FBA orders. Some companies may not want to import shipping costs, since shipping is handled by FBA and Amazon does not pay out the shipping costs to the seller.'
    )

    invoice_fba_orders = fields.Boolean(
        string='Invoice FBA Orders',
        default=False,
        help='Enable automatic invoicing of FBA orders. This will create invoices for FBA orders in Odoo. You must have the "Import FBA Orders" setting enabled for this to work.'
    )


    # FBM Settings
    import_fbm_orders = fields.Boolean(
        string='Import FBM Orders',
        default=False,
        help='Enable automatic import of FBM orders from Amazon. This will create sales orders in Odoo for each FBM order.'
    )

    # AWD Settings
    import_awd_inventory = fields.Boolean(
        string='Import AWD Inventory',
        default=False,
        help='Enable automatic import of AWD inventory from Amazon This will create an AWD warehouse and locations in Odoo, and import the AWD inventory quantities for each product.'
    )

    import_awd_inbound_shipments = fields.Boolean(
        string='Import AWD Inbound Shipments',
        default=False,
        help='Enable automatic import of AWD inbound shipments from Amazon. The origin location of the shipments will be added to the address mapping table. Once mapped the shipments will deduct inventory from the warehouse locations you specified in the address mapping.'
    )

    def verify_connection(self):
        """Verify the account credentials using python-amazon-sp-api."""
        if Sellers is None:
            raise ValidationError('python-amazon-sp-api is not installed.')

        # Clear any cached tokens so that new credentials are always used
        if sp_api_token_cache is not None:
            sp_api_token_cache.clear()
        if sp_api_grantless_cache is not None:
            sp_api_grantless_cache.clear()
        for rec in self:

            if rec.marketplace and isinstance(rec.marketplace, str):
                marketplace = amazon_utils.sp_marketplace_mapper(rec.marketplace)

                amz_credentials = dict(
                    refresh_token=rec.refresh_token,
                    lwa_app_id=rec.app_id,
                    lwa_client_secret=rec.client_secret
                )

                try:
                    found_match = False

                    participation = Sellers(
                        credentials=amz_credentials,
                        marketplace=marketplace,
                    ).get_marketplace_participation()

                    if participation.payload:
                        for part in participation.payload:

                            if part.get('marketplace').get('countryCode') == rec.marketplace:
                                if part.get('participation').get('isParticipating'):
                                    logger.info(f'Connection successful for {rec.name} in {rec.marketplace} marketplace.')
                                    found_match = True
                                    break

                    if not found_match:
                        logger.error(f'No participation found for {rec.name} in {rec.marketplace} marketplace.')
                        raise ValidationError(
                            f'No participation found for {rec.name} in {rec.marketplace} marketplace. \n\n\n\n Data:{participation}'
                        )

                except Exception as e:
                    logger.error(f'Error verifying connection for {rec.name} in {rec.marketplace} marketplace: {e}')
                    raise ValidationError(
                        f'Error verifying connection for {rec.name} in {rec.marketplace} marketplace \n\n\n\n{e}'
                    )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Connection verified successfully.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def verify_and_save(self):
        """Verify connection and persist the record if the credentials succeed."""
        self.ensure_one()
        result = self.verify_connection()
        vals = self._convert_to_write(self._cache)
        if self._origin and self._origin.id:
            self._origin.write(vals)
        else:
            self._origin = self.create(vals)
        result['params']['message'] = _('Connection verified and saved.')
        return result
