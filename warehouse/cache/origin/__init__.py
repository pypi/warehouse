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

from warehouse import db
from warehouse.cache.origin.interfaces import IOriginCache


@db.listens_for(db.Session, "after_flush")
def store_purge_keys(config, session, flush_context):
    cache_keys = config.registry["cache_keys"]

    # We'll (ab)use the session.info dictionary to store a list of pending
    # purges to the session.
    purges = session.info.setdefault("warehouse.cache.origin.purges", set())

    # Go through each new, changed, and deleted object and attempt to store
    # a cache key that we'll want to purge when the session has been committed.
    for obj in (session.new | session.dirty | session.deleted):
        try:
            key_maker = cache_keys[obj.__class__]
        except KeyError:
            continue

        purges.update(key_maker(obj))


@db.listens_for(db.Session, "after_commit")
def execute_purge(config, session):
    purges = session.info.pop("warehouse.cache.origin.purges", set())

    try:
        cacher_factory = config.find_service_factory(IOriginCache)
    except ValueError:
        return

    cacher = cacher_factory(None, config)
    cacher.purge(purges)


def origin_cache(view_or_seconds):
    def inner(view, seconds=None):
        @functools.wraps(view)
        def wrapped(context, request):
            cache_keys = request.registry["cache_keys"]

            try:
                key_maker = cache_keys[context.__class__]
                cacher = request.find_service(IOriginCache)
            except (KeyError, ValueError):
                pass
            else:
                request.add_response_callback(
                    functools.partial(
                        cacher.cache,
                        sorted(key_maker(context)),
                        seconds=seconds,
                    )
                )

            return view(context, request)
        return wrapped

    if callable(view_or_seconds):
        return inner(view_or_seconds)
    else:
        return functools.partial(inner, seconds=view_or_seconds)


def key_maker_factory(keys):
    def key_maker(obj):
        return [k.format(obj=obj) for k in keys]
    return key_maker


def register_origin_cache_keys(config, klass, *keys):
    cache_keys = config.registry.setdefault("cache_keys", {})
    cache_keys[klass] = key_maker_factory(keys)


def includeme(config):
    if "origin_cache.backend" in config.registry.settings:
        cache_class = config.maybe_dotted(
            config.registry.settings["origin_cache.backend"],
        )
        config.register_service_factory(
            cache_class.create_service,
            IOriginCache,
        )

    config.add_directive(
        "register_origin_cache_keys",
        register_origin_cache_keys,
    )
