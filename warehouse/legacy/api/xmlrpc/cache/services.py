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

import redis

from zope.interface import implementer

from warehouse import tasks
from warehouse.legacy.api.xmlrpc import cache
from warehouse.legacy.api.xmlrpc.cache import interfaces


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def purge_tag(task, request, tag):
    service = request.find_service(interfaces.IXMLRPCCache)
    request.log.info('Purging %s', tag)
    try:
        service.purge(tag)
    except (interfaces.CacheError) as exc:
        request.log.error('Error purging %s: %s', tag, str(exc))
        raise task.retry(exc=exc)


@implementer(interfaces.IXMLRPCCache)
class RedisXMLRPCCache:

    def __init__(self, redis_url, purger, redis_db=0, name="lru", expires=None,
                 metric_reporter=None):
        self.redis_conn = redis.StrictRedis.from_url(redis_url, db=redis_db)
        self.redis_lru = cache.RedisLru(self.redis_conn, name=name,
                                        expires=expires,
                                        metric_reporter=metric_reporter)
        self._purger = purger

    @classmethod
    def create_service(cls, context, request):
        return cls(
            request.registry.settings.get('warehouse.xmlrpc.cache.url'),
            request.task(purge_tag).delay,
            name=request.registry.settings.get(
                'warehouse.xmlrpc.cache.name', 'xmlrpc'),
            expires=int(request.registry.settings.get(
                'warehouse.xmlrpc.cache.expires', 25 * 60 * 60))
        )

    def fetch(self, func, args, kwargs, key, tag, expires):
        return self.redis_lru.fetch(func, args, kwargs, key, tag, expires)

    def purge(self, tag):
        return self.redis_lru.purge(tag)

    def purge_tags(self, tags):
        for tag in tags:
            self._purger(tag)


@implementer(interfaces.IXMLRPCCache)
class NullXMLRPCCache:

    def __init__(self, url, purger, **kwargs):
        self._purger = purger

    @classmethod
    def create_service(cls, context, request):
        return cls(
            request.registry.settings.get('warehouse.xmlrpc.cache.url'),
            request.task(purge_tag).delay,
        )

    def fetch(self, func, args, kwargs, key, tag, expires):
        return func(*args, **kwargs)

    def purge(self, tag):
        return

    def purge_tags(self, tags):
        for tag in tags:
            self._purger(tag)
