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

from warehouse.legacy.api.xmlrpc import cache
from warehouse.legacy.api.xmlrpc.cache import interfaces


@implementer(interfaces.IXMLRPCCache)
class RedisXMLRPCCache:

    def __init__(self, redis_url, redis_db=0, name="lru", expires=None,
                 metric_reporter=None):
        self.redis_conn = redis.StrictRedis.from_url(redis_url, db=redis_db)
        self.redis_lru = cache.RedisLru(self.redis_conn, name=name,
                                        expires=expires,
                                        metric_reporter=metric_reporter)

    def fetch(self, func, args, kwargs, key, tag, expires):
        return self.redis_lru.fetch(func, args, kwargs, key, tag, expires)

    def purge(self, tag):
        return self.redis_lru.purge(tag)


@implementer(interfaces.IXMLRPCCache)
class NullXMLRPCCache:

    def __init__(self, *args, **kwargs):
        pass

    def fetch(self, func, args, kwargs, key, tag, expires):
        return func(*args, **kwargs)

    def purge(self, tag):
        return
