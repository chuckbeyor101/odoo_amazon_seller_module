from odoo import models, fields

class ProductProduct(models.Model):
    _inherit = 'product.product'

    amazon_asin = fields.Char(string='ASIN')
    amazon_msku = fields.Char(string='MSKU')
    _sql_constraints = [
        ('amazon_msku_unique', 'unique(amazon_msku)', 'A product with this MSKU already exists.'),
    ]
