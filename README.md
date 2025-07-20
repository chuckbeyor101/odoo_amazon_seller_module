# Amazon Seller Odoo Module

This module integrates Amazon Seller Central with Odoo, providing functionality for managing Amazon products, inventory, and orders.

## Installation

### Prerequisites
- Odoo 18.0 or later
- Python 3.8 or later
- pip package manager

### Steps

1. **Clone the repository to your Odoo addons folder:**
   ```bash
   cd /path/to/your/odoo/addons
   git clone https://github.com/chuckbeyor101/odoo_amazon_seller_module.git amazon_seller
   ```

2. **Install required Python dependencies:**
   ```bash
   pip install python-amazon-sp-api
   ```

3. **Enable Developer Mode in Odoo:**
   - Go to Settings → General Settings
   - Scroll down and click "Activate the developer mode"

4. **Update the App List:**
   - Go to Apps
   - Click "Update Apps List" button
   - Search for "Amazon Seller"

5. **Install the Module:**
   - Find "Amazon Seller" in the apps list
   - Click "Install"

## Configuration

After installation, configure your Amazon Seller account credentials in the module settings to start syncing data.