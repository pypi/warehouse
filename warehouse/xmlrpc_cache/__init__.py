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

import json

from urllib.parse import urlparse

from pyramid.exceptions import ConfigurationError
from redis import StrictRedis
from zope.interface import implementer

from warehouse.xmlrpc_cache.interfaces import IXMLRPCCache, CacheError
from warehouse.xmlrpc_cache.fncache import RedisLru


@implementer(IXMLRPCCache)
class RedisXMLRPCCache:

    def __init__(self, redis_url, redis_db=0, name="lru", expires=None,
                 metric_reporter=None):
        self.redis_conn = StrictRedis.from_url(redis_url, db=redis_db)
        self.redis_lru = RedisLru(self.redis_conn, name=name, expires=expires,
                                  metric_reporter=metric_reporter)

    def fetch(self, func, args, kwargs, key, tag, expires):
        return self.redis_lru.fetch(func, args, kwargs, key, tag, expires)

    def purge(self, tag):
        return self.redis_lru.purge(tag)


@implementer(IXMLRPCCache)
class NullXMLRPCCache:

    def __init__(self, *args, **kwargs):
        pass

    def fetch(self, func, args, kwargs, key, tag, expires):
        return func(*args, **kwargs)

    def purge(self, tag):
        return


def cached_return_view(view, info):
    if info.options.get('xmlrpc_cache'):
        tag = info.options.get('xmlrpc_cache_tag')
        expires = info.options.get('xmlrpc_cache_expires', 86400)
        arg_index = info.options.get('xmlrpc_cache_arg_index')
        slice_obj = info.options.get(
            'xmlrpc_cache_arg_index',
            slice(None, None)
        )

        def wrapper_view(context, request):
            try:
                service = request.find_service(IXMLRPCCache)
            except ValueError:
                return view(context, request)
            try:
                key = json.dumps(request.rpc_args[slice_obj])
                _tag = None
                if arg_index is not None:
                    _tag = tag % (request.rpc_args[arg_index])
                return service.fetch(
                    view, (context, request), {}, key, _tag, expires
                )
            except CacheError:
                return view(context, request)
            response = view(context, request)
            return response
        return wrapper_view
    return view


cached_return_view.options = [
    'xmlrpc_cache',
    'xmlrpc_cache_tag',
    'xmlrpc_cache_expires',
    'xmlrpc_cache_arg_index',
    'xmlrpc_cache_slice_obj',
]


def includeme(config):
    xmlrpc_cache_url = config.registry.settings.get(
        'xmlrpc_cache.url'
    )
    xmlrpc_cache_name = config.registry.settings.get(
        'xmlrpc_cache.name', 'lru'
    )
    xmlrpc_cache_expires = config.registry.settings.get(
        'xmlrpc_cache.expires', 3600
    )

    if xmlrpc_cache_url is None:
        raise ConfigurationError(
            'Cannot configure xlmrpc_cache without xmlrpc_cache.url'
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
