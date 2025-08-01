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

class AmazonListingFees(models.Model):
    _name = 'amazon.listing.fees'
    _description = 'Amazon Listing Fees'
    _auto = False  # Don't create a database table for this model, since it doesn't store data directly

    @api.model
    def cron_get_listing_fees(self):
        """
        Import listing fees from Amazon.
        """

        accounts = self.env['amazon.seller.account'].search([])
        _logger.info('Starting Amazon Listing Fees import cron job for %s account(s)', len(accounts))
        for account in accounts:
            try:
                _logger.info('Importing Listing Fees for account: %s', account.name)

                if account.get_fba_estimated_fees:
                    _logger.info('Fetching FBA estimated fees for account: %s', account.name)
                    self.import_fba_estimated_fees(account)

                if account.get_fbm_estimated_fees:
                    _logger.info('Fetching FBM estimated fees for account: %s', account.name)
                    self.import_fbm_estimated_fees(account)


            except Exception as e:
                _logger.error('Error importing Listing Fees for account %s: %s', account.name, str(e))
                _logger.error(traceback.format_exc())
                raise ValidationError(f'Failed to import Listing Fees for account {account.name}: {str(e)} \n{traceback.format_exc()}')

    def import_fba_estimated_fees(self, account):
        """
        Import FBA estimated fees for products in the account.
        """
        _logger.info('Importing FBA estimated fees for account: %s', account.name)
        products = self.env['product.template'].search([('amazon_asin', '!=', False)])

        for product in products:
            try:
                # Fetch FBA fees
                fees = amazon_utils.get_asin_listing_fees(
                    account, 
                    asin=product.amazon_asin,
                    price=product.list_price, 
                    currency=product.currency_id.name, 
                    is_fba=True
                )
                
                if fees:
                    total_fee_amount = fees.get('FeesEstimateResult', {}).get('FeesEstimate', {}).get('TotalFeesEstimate', {}).get('Amount', 0.0)
                    if not total_fee_amount:
                        _logger.warning(f'No FBA fees found for product {product.name} (ASIN: {product.amazon_asin}).')
                        continue
                    product.amazon_est_fba_fees = total_fee_amount
                    _logger.info(f'FBA estimated fees for {product.name}: {product.amazon_est_fba_fees}')
                    
            except Exception as e:
                _logger.error(f'Error fetching FBA estimated fees for product {product.name}: {str(e)}')
                raise ValidationError(f'Failed to fetch FBA estimated fees for product {product.name}: {str(e)}')
            

    def import_fbm_estimated_fees(self, account):
        """
        Import FBM estimated fees for products in the account.
        """
        _logger.info('Importing FBM estimated fees for account: %s', account.name)
        products = self.env['product.template'].search([('amazon_asin', '!=', False)])

        for product in products:
            try:
                # Fetch FBM fees
                fees = amazon_utils.get_asin_listing_fees(
                    account, 
                    asin=product.amazon_asin,
                    price=product.list_price, 
                    currency=product.currency_id.name, 
                    is_fba=False
                )
                
                if not fees:
                    _logger.warning(f'No FBM fees found for product {product.name} (ASIN: {product.amazon_asin}).')
                    continue

                total_fee_amount = fees.get('FeesEstimateResult', {}).get('FeesEstimate', {}).get('TotalFeesEstimate', {}).get('Amount', 0.0)
                if not total_fee_amount:
                    _logger.warning(f'No FBM fees found for product {product.name} (ASIN: {product.amazon_asin}).')
                    continue
                product.amazon_est_fbm_fees = total_fee_amount
                _logger.info(f'FBM estimated fees for {product.name}: {product.amazon_est_fbm_fees}')
                    
            except Exception as e:
                _logger.error(f'Error fetching FBM estimated fees for product {product.name}: {str(e)}')
                raise ValidationError(f'Failed to fetch FBM estimated fees for product {product.name}: {str(e)}')