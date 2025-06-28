{
    'name': 'Amazon Seller',
    'version': '1.0',
    'summary': 'Manage Amazon seller accounts',
    'description': 'Stores multiple Amazon seller accounts and credentials.',
    'category': 'Sales',
    'author': 'Your Company',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/amazon_seller_account_views.xml',
    ],
    'installable': True,
    'application': False,
}
