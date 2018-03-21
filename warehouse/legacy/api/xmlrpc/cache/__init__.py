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

from urllib.parse import urlparse

from pyramid.exceptions import ConfigurationError

from .fncache import RedisLru
from .derivers import cached_return_view
from .services import (
    NullXMLRPCCache,
    RedisXMLRPCCache,
)
from .interfaces import IXMLRPCCache

__all__ = [
    "RedisLru",
]


def includeme(config):
    xmlrpc_cache_url = config.registry.settings.get(
        'warehouse.xmlrpc.cache.url'
    )
    xmlrpc_cache_name = config.registry.settings.get(
        'warehouse.xmlrpc.cache.name', 'xmlrpc'
    )
    xmlrpc_cache_expires = config.registry.settings.get(
        'warehouse.xmlrpc.cache.expires', 25 * 60 * 60
    )

    if xmlrpc_cache_url is None:
        raise ConfigurationError(
            'Cannot configure xlmrpc_cache without warehouse.xmlrpc.cache.url'
        )

    xmlrpc_cache_url_scheme = urlparse(xmlrpc_cache_url).scheme
    if xmlrpc_cache_url_scheme in ('redis', 'rediss'):
        xmlrpc_cache_class = RedisXMLRPCCache
    elif xmlrpc_cache_url_scheme in ('null'):
        xmlrpc_cache_class = NullXMLRPCCache
    else:
        raise ConfigurationError(
            f'Unknown XMLRPCCache scheme: {xmlrpc_cache_url_scheme}'
        )

    try:
        xmlrpc_cache_expires = int(xmlrpc_cache_expires)
    except ValueError:
        raise ConfigurationError(
            f'Unable to cast XMLRPCCache expires "{xmlrpc_cache_expires}" '
            ' to integer'
        )

    xmlrpc_cache = xmlrpc_cache_class(
        xmlrpc_cache_url,
        name=xmlrpc_cache_name,
        expires=xmlrpc_cache_expires,
    )

    config.register_service(xmlrpc_cache, iface=IXMLRPCCache)
    config.add_view_deriver(
        cached_return_view, under='rendered_view', over='mapped_view'
    )
