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

import functools

from warehouse.cache.origin.interfaces import IOriginCache


def origin_cache(view):
    @functools.wraps(view)
    def wrapped(context, request):
        cache_keys = request.registry["cache_keys"]

        try:
            key_maker = cache_keys[context.__class__]
            cacher = request.find_service(IOriginCache)
        except (KeyError, ValueError):
            pass
        else:
            keys = key_maker(context)
            request.add_response_callback(
                functools.partial(cacher.cache, sorted(keys))
            )

        return view(context, request)
    return wrapped


def key_maker_factory(keys):
    def key_maker(obj):
        return [k.format(obj=obj) for k in keys]
    return key_maker


def register_origin_cache_keys(config, klass, *keys):
    cache_keys = config.registry.setdefault("cache_keys", {})
    cache_keys[klass] = key_maker_factory(keys)


def includeme(config):
    config.add_directive(
        "register_origin_cache_keys",
        register_origin_cache_keys,
    )
