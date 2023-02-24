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

import itertools
import time
import urllib.parse

import forcediphttpsadapter.adapters
import redis
import requests

from zope.interface import implementer

from warehouse import tasks
from warehouse.cache.origin.interfaces import IOriginCache
from warehouse.metrics.interfaces import IMetricsService


class UnsuccessfulPurgeError(Exception):
    pass


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def batch_purge(task, request, key):
    """Cron job to pull all pending purges out of redis"""
    cacher = request.find_service(IOriginCache)

    try:
        cacher.purge_batched_keys()
    except (
        requests.ConnectionError,
        requests.HTTPError,
        requests.Timeout,
        UnsuccessfulPurgeError,
    ) as exc:
        request.log.error("Error purging %s: %s", key, str(exc))
        raise task.retry(exc=exc)


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def purge_key(task, request, key):
    cacher = request.find_service(IOriginCache)
    metrics = request.find_service(IMetricsService, context=None)
    request.log.info("Purging %s", key)
    try:
        cacher.purge_key(key, metrics=metrics)
    except (
        requests.ConnectionError,
        requests.HTTPError,
        requests.Timeout,
        UnsuccessfulPurgeError,
    ) as exc:
        request.log.error("Error purging %s: %s", key, str(exc))
        raise task.retry(exc=exc)


@implementer(IOriginCache)
class FastlyCache:
    def __init__(
        self, *, api_endpoint, api_connect_via, api_key, redis_url, service_id, purger
    ):
        self.api_endpoint = api_endpoint
        self.api_connect_via = api_connect_via
        self.api_key = api_key
        self.service_id = service_id

        self.redis = redis.StrictRedis.from_url(redis_url)

    def get_batch_purge_keys(self):

        pass

    @classmethod
    def create_service(cls, context, request):
        return cls(
            api_endpoint=request.registry.settings.get(
                "origin_cache.api_endpoint", "https://api.fastly.com"
            ),
            api_connect_via=request.registry.settings.get(
                "origin_cache.api_connect_via", None
            ),
            api_key=request.registry.settings["origin_cache.api_key"],
            redis_url=request.registry.settings["origin_cache.redis_url"],
            service_id=request.registry.settings["origin_cache.service_id"],
        )

    def cache(
        self,
        keys,
        request,
        response,
        *,
        seconds=None,
        stale_while_revalidate=None,
        stale_if_error=None,
    ):
        existing_keys = set(response.headers.get("Surrogate-Key", "").split())

        response.headers["Surrogate-Key"] = " ".join(sorted(set(keys) | existing_keys))

        values = []

        if seconds is not None:
            values.append(f"max-age={seconds}")

        if stale_while_revalidate is not None:
            values.append(f"stale-while-revalidate={stale_while_revalidate}")

        if stale_if_error is not None:
            values.append(f"stale-if-error={stale_if_error}")

        if values:
            response.headers["Surrogate-Control"] = ", ".join(values)

    def purge(self, keys):
        timestamp = int(time.time()) % 10
        self.redis.sadd(f"batch-purge:{timestamp}", *keys)

    def _purge_key(self, key, connect_via=None):
        path = "/service/{service_id}/purge/{key}".format(
            service_id=self.service_id, key=key
        )
        url = urllib.parse.urljoin(self.api_endpoint, path)
        headers = {
            "Accept": "application/json",
            "Fastly-Key": self.api_key,
            "Fastly-Soft-Purge": "1",
        }

        session = requests.Session()

        if connect_via is not None:
            session.mount(
                self.api_endpoint,
                forcediphttpsadapter.adapters.ForcedIPHTTPSAdapter(
                    dest_ip=self.api_connect_via
                ),
            )

        resp = session.post(url, headers=headers)
        resp.raise_for_status()
        if resp.json().get("status") != "ok":
            raise UnsuccessfulPurgeError(f"Could not purge {key!r}")

    def _double_purge_key(self, key, connect_via=None):
        self._purge_key(key, connect_via=connect_via)
        # https://developer.fastly.com/learning/concepts/purging/#race-conditions
        time.sleep(2)
        self._purge_key(key, connect_via=connect_via)

    def purge_key(self, key, metrics=None):
        try:
            self._purge_key(key, connect_via=self.api_connect_via)
        except requests.ConnectionError:
            if self.api_connect_via is None:
                raise
            else:
                metrics.increment(
                    "warehouse.cache.origin.fastly.connect_via.failed",
                    tags=[f"ip_address:{self.api_connect_via}"],
                )
                self._double_purge_key(key)  # Do not connect via on fallback

    def _purge_multiple_keys(self, keys):
        path = "/service/{service_id}/purge/".format(service_id=self.service_id)
        url = urllib.parse.urljoin(self.api_endpoint, path)
        headers = {
            "Accept": "application/json",
            "Fastly-Key": self.api_key,
            "Fastly-Soft-Purge": "1",
        }
        session = requests.Session()
        data = {"surrogate_keys": list(keys)}

        resp = session.post(url, headers=headers, data=data)

        resp.raise_for_status()
        if resp.json().get("status") != "ok":
            raise UnsuccessfulPurgeError(f"Could not purge {len(keys)!r}")

    def purge_batched_keys(self, keys, metrics=None):
        # list all batches older than current timestamp, ordered by key/timestamp
        timestamp = int(time.time()) % 10
        batch_keys = [
            key
            for key in sorted(redis.keys(pattern="batch-purge:*"))
            if key.split(":")[1] < str(timestamp)
        ]

        # for each batch, purge at most 256 at a time, and remove from the batch
        for batch_key in batch_keys:
            keys_to_purge = self.redis.smembers(batch_key)
            for key_chunk in itertools.chunked(keys_to_purge, 256):
                self.purge_multiple_keys(key_chunk)
                self.redis.srem(batch_key, *key_chunk)
