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


# This is a hack to make `warehouse init` work. We need a SECRET_KEY defined but
#   we don't want to declare a default one. This will only declare one if
#   WAREHOUSE_CONF is none (E.g. we are running on strictly default settings).
if "WAREHOUSE_CONF" not in os.environ:
    SECRET_KEY = "INSECURE, DO NOT USE"
