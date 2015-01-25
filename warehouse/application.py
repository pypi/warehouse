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

from pyramid.config import Configurator

from warehouse.utils.mapper import WarehouseMapper


def configure():
    config = Configurator()

    # Setup our custom view mapper, this will provide two things:
    #   * Enable using view functions as asyncio coroutines.
    #   * Pass matched items from views in as keyword arguments to the
    #     function.
    config.set_view_mapper(WarehouseMapper)

    # Register the configuration for each sub package.
    config.include(".project", route_prefix="/project/")

    # Scan everything for configuration
    config.scan()

    return config
