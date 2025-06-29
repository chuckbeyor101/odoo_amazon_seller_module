{
    # Basic module metadata used by Odoo
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
    # Install the python-amazon-sp-api package when the module is installed
    'post_init_hook': '_install_python_dependencies',
    'installable': True,
    'application': True,
}
