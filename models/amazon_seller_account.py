import subprocess
import sys

from odoo import models, fields, api
from odoo.exceptions import ValidationError

try:
    from sp_api.api import Sellers
    from sp_api.base import Marketplaces, SellingApiException
except Exception:
    Sellers = None
    Marketplaces = None
    SellingApiException = Exception


class AmazonSellerAccount(models.Model):
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
        ('UK', 'United Kingdom'),
        ('DE', 'Germany'),
        ('FR', 'France'),
        ('IT', 'Italy'),
        ('ES', 'Spain'),
    ], string='Marketplace', required=True, default='US')

    def verify_connection(self):
        """Verify the account credentials using python-amazon-sp-api."""
        if Sellers is None:
            raise ValidationError('python-amazon-sp-api is not installed.')
        for rec in self:
            marketplace = getattr(Marketplaces, rec.marketplace, None)
            try:
                Sellers(
                    refresh_token=rec.refresh_token,
                    lwa_app_id=rec.app_id,
                    lwa_client_secret=rec.client_secret,
                    account=rec.seller_id,
                    marketplace=marketplace,
                ).get_marketplace_participations()
            except SellingApiException as exc:
                raise ValidationError(
                    f'Connection failed for {rec.name}: {exc}'
                )
        return True
