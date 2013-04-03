import os

from warehouse.__about__ import *

# Force the DJANGO_SETTINGS_MODULE environment variable to
#   warehouse.conf.loader which handles loading settings in Warehouse.
os.environ["DJANGO_SETTINGS_MODULE"] = "warehouse.conf.loader"
