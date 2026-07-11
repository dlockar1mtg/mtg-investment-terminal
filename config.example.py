"""Safe local configuration example.

Copy this file to config_local.py for machine-specific settings.
config_local.py is excluded from Git.
"""

import os

TCGPLAYER_ACCESS_TOKEN = os.getenv("TCGPLAYER_ACCESS_TOKEN", "")
