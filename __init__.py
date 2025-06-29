# Expose all model classes to Odoo
from . import models

def _install_python_dependencies(cr, registry):
    """Install required python packages when the module is installed."""
    import subprocess
    import sys

    subprocess.call([
        sys.executable,
        '-m',
        'pip',
        'install',
        'python-amazon-sp-api'
    ])
