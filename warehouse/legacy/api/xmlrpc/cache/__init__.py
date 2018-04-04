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

import collections

from urllib.parse import urlparse

from pyramid.exceptions import ConfigurationError
from sqlalchemy.orm.base import NO_VALUE
from sqlalchemy.orm.session import Session

from warehouse import db
from warehouse.accounts.models import Email, User
from warehouse.legacy.api.xmlrpc.cache.fncache import RedisLru
from warehouse.legacy.api.xmlrpc.cache.derivers import cached_return_view
from warehouse.legacy.api.xmlrpc.cache.services import (
    NullXMLRPCCache,
    RedisXMLRPCCache,
)
from warehouse.legacy.api.xmlrpc.cache.interfaces import IXMLRPCCache

__all__ = [
    "RedisLru",
]


CacheKeys = collections.namedtuple("CacheKeys", ["cache", "purge"])


def receive_set(attribute, config, target):
    cache_keys = config.registry["cache_keys"]
    session = Session.object_session(target)
    purges = session.info.setdefault(
        "warehouse.legacy.api.xmlrpc.cache.purges",
        set()
    )
    key_maker = cache_keys[attribute]
    keys = key_maker(target).purge
    purges.update(list(keys))


@db.listens_for(db.Session, "after_flush")
def store_purge_keys(config, session, flush_context):
    cache_keys = config.registry["cache_keys"]

    # We'll (ab)use the session.info dictionary to store a list of pending
    # purges to the session.
    purges = session.info.setdefault(
        "warehouse.legacy.api.xmlrpc.cache.purges", set()
    )

    # Go through each new, changed, and deleted object and attempt to store
    # a cache key that we'll want to purge when the session has been committed.
    for obj in (session.new | session.dirty | session.deleted):
        try:
            key_maker = cache_keys[obj.__class__]
        except KeyError:
            continue

        purges.update(key_maker(obj).purge)


@db.listens_for(db.Session, "after_commit")
def execute_purge(config, session):
    purges = session.info.pop(
        "warehouse.legacy.api.xmlrpc.cache.purges", set()
    )

    try:
        xmlrpc_cache_factory = config.find_service_factory(IXMLRPCCache)
    except ValueError:
        return

    xmlrpc_cache = xmlrpc_cache_factory(None, config)
    xmlrpc_cache.purge_tags(purges)


@db.listens_for(User.name, 'set')
def user_name_receive_set(config, target, value, oldvalue, initiator):
    if oldvalue is not NO_VALUE:
        receive_set(User.name, config, target)


@db.listens_for(Email.primary, 'set')
def email_primary_receive_set(config, target, value, oldvalue, initiator):
    if oldvalue is not NO_VALUE:
        receive_set(Email.primary, config, target)


def includeme(config):
    xmlrpc_cache_url = config.registry.settings.get(
        'warehouse.xmlrpc.cache.url'
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

    config.register_service_factory(
        xmlrpc_cache_class.create_service,
        iface=IXMLRPCCache
    )
    config.add_view_deriver(
        cached_return_view, under='rendered_view', over='mapped_view'
    )
