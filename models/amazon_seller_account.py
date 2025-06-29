import subprocess
import sys
import logging

from odoo import models, fields, api
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

                            logger.info(participation.payload)

                            if part.get('marketplace').get('countryCode') == rec.marketplace:
                                if part.get('participation').get('isParticipating'):
                                    logger.info(f'Connection successful for {rec.name} in {rec.marketplace} marketplace.')
                                    # TODO Show success message to user
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

        return True
