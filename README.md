# Amazon Seller Module

This Odoo module provides a basic framework for managing multiple Amazon
seller accounts. Each account stores the following credentials:

- **App ID**
- **Client Secret**
- **Refresh Token**
- **Seller ID**
- **Marketplace** - selectable region where the account operates

The module attempts to install the `python-amazon-sp-api` package during installation.
After configuring an account, use the *Verify Connection* button to confirm that the provided credentials work with Amazon's Selling Partner API.
