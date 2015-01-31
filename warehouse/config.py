# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import os.path

from pyramid.config import Configurator

from warehouse.utils.mapper import WarehouseMapper


def configure(settings=None):
    if settings is None:
        settings = {}

    # Set our yml.location so that it contains all of our settings files
    settings["yml.location"] = ["warehouse:etc"]

    # Pull our configuration location of the environment
    if "WAREHOUSE_CONFIG_DIR" in os.environ:
        settings["yml.location"].append(
            os.path.abspath(os.environ["WAREHOUSE_CONFIG_DIR"])
        )

    # Pull our configuration environment of the environment
    if "WAREHOUSE_ENV" in os.environ:
        settings["env"] = os.environ["WAREHOUSE_ENV"]

    config = Configurator(settings=settings)

    # Setup our custom view mapper, this will provide two things:
    #   * Enable using view functions as asyncio coroutines.
    #   * Pass matched items from views in as keyword arguments to the
    #     function.
    config.set_view_mapper(WarehouseMapper)

    # We want to load configuration from YAML files
    config.include("tzf.pyramid_yml")

    # We'll want to use Jinja2 as our template system.
    config.include("pyramid_jinja2")

    # We also want to use Jinja2 for .html templates as well, because we just
    # assume that all templates will be using Jinja.
    config.add_jinja2_renderer(".html")

    # We'll store all of our templates in one location, warehouse/templates
    # so we'll go ahead and add that to the Jinja2 search path.
    config.add_jinja2_search_path("warehouse:templates", name=".html")

    # Register the configuration for the PostgreSQL database.
    config.include(".db")

    # Register the configuration for each sub package.
    config.include(".project", route_prefix="/project/")

    # Scan everything for configuration
    config.scan()

    return config
