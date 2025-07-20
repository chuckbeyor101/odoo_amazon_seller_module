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

{
    'name': 'Amazon Seller',
    'version': '1.1.1',
    'summary': 'Manage Amazon seller accounts',
    'description': '''This module allows you to manage Amazon seller accounts.

Licensed under Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International.
To view a copy of this license, visit https://creativecommons.org/licenses/by-nc-sa/4.0/''',
    'author': 'Charles L Beyor and Beyotek Inc.',
    'license': 'Other proprietary',
    'depends': ['base', 'stock', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/amazon_overview_views.xml',
        'views/amazon_seller_account_views.xml',
        'views/amazon_address_map_views.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'data/cron.xml',
    ],
    'installable': True,
    'application': True,
}
