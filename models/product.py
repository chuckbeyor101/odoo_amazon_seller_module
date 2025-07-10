from odoo import models, fields


class ProductProduct(models.Model):
    _inherit = 'product.product'

    amazon_asin = fields.Char(string='ASIN')

    _sql_constraints = [
        (
            'amazon_asin_unique',
            'unique(amazon_asin)',
            'A product with this ASIN already exists.',
        ),
    ]
