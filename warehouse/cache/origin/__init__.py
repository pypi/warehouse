# SPDX-License-Identifier: Apache-2.0

import collections
import functools
import operator

from itertools import chain

import structlog

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable

from warehouse import db
from warehouse.cache.origin.derivers import html_cache_deriver
from warehouse.cache.origin.interfaces import IOriginCache
from warehouse.utils.db import orm_session_from_obj

logger = structlog.get_logger(__name__)


@db.listens_for(db.Session, "after_flush")
def store_purge_keys(config, session, flush_context):
    cache_keys = config.registry["cache_keys"]

    # We'll (ab)use the session.info dictionary to store a list of pending
    # purges to the session.
    purges = session.info.setdefault("warehouse.cache.origin.purges", set())

    # Go through each new, changed, and deleted object and attempt to store
    # a cache key that we'll want to purge when the session has been committed.
    for obj in session.new | session.dirty | session.deleted:
        try:
            key_maker = cache_keys[obj.__class__]
        except KeyError:
            continue

        keys = list(key_maker(obj).purge)

        if keys:
            if obj in session.new:
                state = "new"
            elif obj in session.deleted:
                state = "deleted"
            else:
                state = "dirty"

            log_kw = {
                "obj_class": obj.__class__.__name__,
                "state": state,
                "keys": sorted(keys),
            }
            if state == "dirty":
                try:
                    changed = sorted(sa_inspect(obj).committed_state.keys())
                except NoInspectionAvailable:
                    changed = []
                if changed:
                    log_kw["changed_attrs"] = changed
            logger.info("cache_purge_keys_generated", **log_kw)

        purges.update(keys)


@db.listens_for(db.Session, "after_commit")
def execute_purge(config, session):
    purges = session.info.pop("warehouse.cache.origin.purges", set())

    if not purges:
        return

    try:
        cacher_factory = config.find_service_factory(IOriginCache)
    except LookupError:
        return

    logger.info("cache_purge_executing", count=len(purges), keys=sorted(purges))

    cacher = cacher_factory(None, config)
    cacher.purge(purges)


def origin_cache(seconds, keys=None, stale_while_revalidate=None, stale_if_error=None):
    if keys is None:
        keys = []

    def inner(view):
        @functools.wraps(view)
        def wrapped(context, request):
            cache_keys = request.registry["cache_keys"]

            context_keys = []
            if context.__class__ in cache_keys:
                context_keys = cache_keys[context.__class__](context).cache

            try:
                cacher = request.find_service(IOriginCache)
            except LookupError:
                pass
            else:
                request.add_response_callback(
                    functools.partial(
                        cacher.cache,
                        context_keys + keys,
                        seconds=seconds,
                        stale_while_revalidate=stale_while_revalidate,
                        stale_if_error=stale_if_error,
                    )
                )

            return view(context, request)

        return wrapped

    return inner


CacheKeys = collections.namedtuple("CacheKeys", ["cache", "purge"])


def key_factory(keystring, iterate_on=None, if_attr_exists=None):
    def generate_key(obj):
        if iterate_on:
            for itr in operator.attrgetter(iterate_on)(obj):
                yield keystring.format(itr=itr, obj=obj)
        elif if_attr_exists:
            try:
                attr = operator.attrgetter(if_attr_exists)(obj)
                yield keystring.format(attr=attr, obj=obj)
            except AttributeError:
                pass
        else:
            yield keystring.format(obj=obj)

    return generate_key


def key_maker_factory(cache_keys, purge_keys):
    if cache_keys is None:
        cache_keys = []

    if purge_keys is None:
        purge_keys = []

    def key_maker(obj):
        return CacheKeys(
            # Note: this does not support setting the `cache` argument via
            # multiple `key_factories` as we do with `purge` because there is
            # a limit to how many surrogate keys we can attach to a single HTTP
            # response, and being able to use use `iterate_on` would allow this
            # size to be unbounded.
            # ref: https://github.com/pypi/warehouse/pull/3189
            cache=[k.format(obj=obj) for k in cache_keys],
            purge=chain.from_iterable(key(obj) for key in purge_keys),
        )

    return key_maker


def register_origin_cache_keys(config, klass, cache_keys=None, purge_keys=None):
    key_makers = config.registry.setdefault("cache_keys", {})
    key_makers[klass] = key_maker_factory(cache_keys=cache_keys, purge_keys=purge_keys)


def receive_set(attribute, config, target):
    cache_keys = config.registry["cache_keys"]
    session = orm_session_from_obj(target)
    purges = session.info.setdefault("warehouse.cache.origin.purges", set())
    key_maker = cache_keys[attribute]
    keys = list(key_maker(target).purge)
    logger.info(
        "cache_purge_keys_generated",
        obj_class=target.__class__.__name__,
        trigger="attribute_set",
        attr=attribute.key,
        keys=sorted(keys),
    )
    purges.update(keys)


def includeme(config):
    if "origin_cache.backend" in config.registry.settings:
        cache_class = config.maybe_dotted(
            config.registry.settings["origin_cache.backend"]
        )
        config.register_service_factory(cache_class.create_service, IOriginCache)
        config.add_view_deriver(html_cache_deriver)

    config.add_directive("register_origin_cache_keys", register_origin_cache_keys)
