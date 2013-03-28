import os
import yaml


def load_yaml_config(conffile, environment):
    config = {}

    if conffile:
        # Open the given YAML file with UTF-8 and safely load it
        with open(conffile, "r", encoding="utf-8") as cfile:
            loaded = yaml.safe_load(cfile)

        # Pull out the environment specific configuration and sanitize for
        #   UPPERCASSED attributes only.
        config = {
                key: value
                for key, value in loaded.get(environment.upper(), {}).items()
                if key == key.upper()
            }

    return config

# Load the default settings
from warehouse.conf.defaults import *

# Load the configuration from WAREHOUSE_CONF
globals().update(
    load_yaml_config(
        os.environ.get("WAREHOUSE_CONF", None),
        os.environ.get("WAREHOUSE_ENV", "DEVELOPMENT"),
    )
)
