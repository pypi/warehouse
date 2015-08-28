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

import celery.exceptions
import pretend
import pytest
import requests

from zope.interface.verify import verifyClass

from warehouse.cache.origin import fastly
from warehouse.cache.origin.interfaces import IOriginCache


class TestPurgeKey:

    def test_purges_successfully(self, monkeypatch):
        task = pretend.stub()
        cacher = pretend.stub(purge_key=pretend.call_recorder(lambda k: None))
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda iface: cacher),
        )

        fastly.purge_key.__wrapped__.__func__(task, request, "foo")

        assert request.find_service.calls == [pretend.call(IOriginCache)]
        assert cacher.purge_key.calls == [pretend.call("foo")]

    @pytest.mark.parametrize(
        "exception_type",
        [
            requests.ConnectionError,
            requests.HTTPError,
            requests.Timeout,
            fastly.UnsuccessfulPurge,
        ],
    )
    def test_purges_fails(self, monkeypatch, exception_type):
        exc = exception_type()

        class Cacher:
            @staticmethod
            @pretend.call_recorder
            def purge_key(key):
                raise exc

        class Task:
            @staticmethod
            @pretend.call_recorder
            def retry(exc):
                raise celery.exceptions.Retry

        task = Task()
        cacher = Cacher()
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda iface: cacher),
        )

        with pytest.raises(celery.exceptions.Retry):
            fastly.purge_key.__wrapped__.__func__(task, request, "foo")

        assert request.find_service.calls == [pretend.call(IOriginCache)]
        assert cacher.purge_key.calls == [pretend.call("foo")]
        assert task.retry.calls == [pretend.call(exc=exc)]


class TestFastlyCache:

    def test_verify_service(self):
        assert verifyClass(IOriginCache, fastly.FastlyCache)

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "origin_cache.api_key": "the api key",
                    "origin_cache.service_id": "the service id",
                },
            ),
        )
        cacher = fastly.FastlyCache.create_service(None, request)
        assert isinstance(cacher, fastly.FastlyCache)
        assert cacher.api_key == "the api key"
        assert cacher.service_id == "the service id"

    def test_adds_surrogate_key(self):
        request = pretend.stub()
        response = pretend.stub(headers={})

        cacher = fastly.FastlyCache(api_key=None, service_id=None)
        cacher.cache(["abc", "defg"], request, response)

        assert response.headers == {"Surrogate-Key": "abc defg"}

    def test_adds_surrogate_control(self):
        request = pretend.stub()
        response = pretend.stub(headers={})

        cacher = fastly.FastlyCache(api_key=None, service_id=None)
        cacher.cache(
            ["abc", "defg"],
            request,
            response,
            seconds=9123,
            stale_while_revalidate=4567,
            stale_if_error=2276,
        )

        assert response.headers == {
            "Surrogate-Key": "abc defg",
            "Surrogate-Control": (
                "max-age=9123, stale-while-revalidate=4567, "
                "stale-if-error=2276"
            ),
        }

    def test_purge(self, monkeypatch):
        cacher = fastly.FastlyCache(
            api_key="an api key",
            service_id="the-service-id",
        )

        purge_delay = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(fastly.purge_key, "delay", purge_delay)

        cacher.purge(["one", "two"])

        assert purge_delay.calls == [pretend.call("one"), pretend.call("two")]

    def test_purge_key_ok(self, monkeypatch):
        cacher = fastly.FastlyCache(
            api_key="an api key",
            service_id="the-service-id",
        )

        response = pretend.stub(
            raise_for_status=pretend.call_recorder(lambda: None),
            json=lambda: {"status": "ok"},
        )
        requests_post = pretend.call_recorder(lambda *a, **kw: response)
        monkeypatch.setattr(requests, "post", requests_post)

        cacher.purge_key("one")

        assert requests_post.calls == [
            pretend.call(
                "https://api.fastly.com/service/the-service-id/purge/one",
                headers={
                    "Accept": "application/json",
                    "Fastly-Key": "an api key",
                    "Fastly-Soft-Purge": "1",
                },
            ),
        ]
        assert response.raise_for_status.calls == [pretend.call()]

    @pytest.mark.parametrize("result", [{"status": "fail"}, {}])
    def test_purge_key_unsuccessful(self, monkeypatch, result):
        cacher = fastly.FastlyCache(
            api_key="an api key",
            service_id="the-service-id",
        )

        response = pretend.stub(
            raise_for_status=pretend.call_recorder(lambda: None),
            json=lambda: result,
        )
        requests_post = pretend.call_recorder(lambda *a, **kw: response)
        monkeypatch.setattr(requests, "post", requests_post)

        with pytest.raises(fastly.UnsuccessfulPurge):
            cacher.purge_key("one")

        assert requests_post.calls == [
            pretend.call(
                "https://api.fastly.com/service/the-service-id/purge/one",
                headers={
                    "Accept": "application/json",
                    "Fastly-Key": "an api key",
                    "Fastly-Soft-Purge": "1",
                },
            ),
        ]
        assert response.raise_for_status.calls == [pretend.call()]
