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

import subprocess
import sys

# Ensure Pip is available
try:
    import pip
except ImportError:
    # Install pip with upgrade if not available
    subprocess.call([sys.executable, '-m', 'ensurepip', '--upgrade'])

# Install the python-amazon-sp-api package
subprocess.call([
    sys.executable,
    '-m',
    'pip',
    'install',
    'python-amazon-sp-api',
    '--break-system-packages',
])

from . import models

