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

_logger = logging.getLogger(__name__)


class AmazonAddressMap(models.Model):
    _name = 'amazon.address.map'
    _description = 'Amazon Address to Warehouse Mapping'
    _rec_name = 'display_name'
    _order = 'name, city, state_or_region'

    # Basic Information
    name = fields.Char(
        string='Contact Name',
        required=True,
        help='Name of the contact person'
    )
    
    # Address Fields
    address_line1 = fields.Char(
        string='Address Line 1',
        required=True,
        help='Primary address line'
    )
    address_line2 = fields.Char(
        string='Address Line 2',
        help='Secondary address line (apartment, suite, etc.)'
    )
    city = fields.Char(
        string='City',
        required=True,
        help='City name'
    )
    state_or_region = fields.Char(
        string='State/Region',
        required=True,
        help='State or region code/name'
    )
    postal_code = fields.Char(
        string='Postal Code',
        required=True,
        help='ZIP or postal code'
    )
    country_code = fields.Char(
        string='Country Code',
        required=True,
        default='US',
        help='Two-letter country code (e.g., US, CA, GB)'
    )
    phone_number = fields.Char(
        string='Phone Number',
        help='Contact phone number'
    )
    
    # Warehouse Location Mapping
    warehouse_loc = fields.Many2one(
        'stock.location',
        string='Mapped Warehouse Location',
        domain=[('usage', '=', 'internal')],
        help='Warehouse location this address is mapped to'
    )
    
    # Tracking
    create_date = fields.Datetime(string='Created Date', readonly=True)
    write_date = fields.Datetime(string='Last Updated', readonly=True)
    
    # Computed Fields
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    
    @api.depends('name', 'city', 'state_or_region', 'warehouse_loc')
    def _compute_display_name(self):
        for record in self:
            if record.warehouse_loc:
                record.display_name = f"{record.name} - {record.city}, {record.state_or_region} → {record.warehouse_loc.name}"
            else:
                record.display_name = f"{record.name} - {record.city}, {record.state_or_region} (No Location)"
    
    @api.model
    def get_warehouse_location_else_create(self, name:str="", address_line1:str="", address_line2:str="", city:str="", state_or_region:str="", postal_code:str="", country_code:str=""):
        # Find a address map 
            awd_address_map = self.env['amazon.address.map'].search([
                ('name', '=', name),
                ('address_line1', '=', address_line1),
                ('address_line2', '=', address_line2),
                ('city', '=', city),
                ('state_or_region', '=', state_or_region),
                ('postal_code', '=', postal_code),
                ('country_code', '=', country_code),
            ], limit=1)

            if awd_address_map and awd_address_map.warehouse_loc:
                _logger.debug('Found address map')
                return awd_address_map.warehouse_loc
            
            elif awd_address_map:
                _logger.warning('Address map found but no warehouse location is assigned.')
                return None
            
            else:
                # add the address map to the database
                _logger.warning('No address map found.')
                try:
                    self.env['amazon.address.map'].create({
                        'name': name,
                        'address_line1': address_line1,
                        'address_line2': address_line2,
                        'city': city,
                        'state_or_region': state_or_region,
                        'postal_code': postal_code,
                        'country_code': country_code,
                    })
                except Exception as e:
                    _logger.error('Failed to create address map: %s', str(e))
                    return None
