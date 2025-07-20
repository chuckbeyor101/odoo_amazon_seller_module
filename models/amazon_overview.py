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

from odoo import models, fields, api

class AmazonOverview(models.TransientModel):
    """Amazon Seller Overview Dashboard"""
    
    _name = 'amazon.overview'
    _description = 'Amazon Seller Overview'
    
    # Summary fields
    total_accounts = fields.Integer(string='Total Accounts', readonly=True)
    total_address_mappings = fields.Integer(string='Address Mappings', readonly=True)
    unmapped_addresses = fields.Integer(string='Unmapped Addresses', readonly=True)
    has_unmapped_addresses = fields.Boolean(string='Has Unmapped Addresses', readonly=True)
    
    @api.model
    def default_get(self, fields_list):
        """Populate overview data"""
        result = super().default_get(fields_list)
        
        # Count total accounts
        total_accounts = self.env['amazon.seller.account'].search_count([])
        result['total_accounts'] = total_accounts
        
        # Count address mappings
        address_mappings = self.env['amazon.address.map'].search_count([])
        result['total_address_mappings'] = address_mappings
        
        # Count unmapped addresses (addresses without warehouse location)
        unmapped_addresses = self.env['amazon.address.map'].search_count([
            ('warehouse_loc', '=', False)
        ])
        result['unmapped_addresses'] = unmapped_addresses
        result['has_unmapped_addresses'] = unmapped_addresses > 0
        
        return result
