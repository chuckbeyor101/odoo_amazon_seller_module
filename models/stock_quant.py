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
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class StockQuant(models.Model):
    _inherit = 'stock.quant'


    def set_available_quantity(self, product, location, quantity:int, log_prefix:str=""):
        """
        Set the available quantity for a product at a specific location.
        This method overrides the default behavior to ensure that the
        available quantity is updated correctly.
        """
        current_qty = self._get_available_quantity(product, location)
        qty_delta = quantity - current_qty
        
        if qty_delta != 0:
            self._update_available_quantity(product, location, quantity=qty_delta)
            _logger.info(log_prefix + 'Updated available quantity for %s in %s: %s -> %s (delta: %s)', 
                         product.name, location.name, current_qty, quantity, qty_delta)

 
