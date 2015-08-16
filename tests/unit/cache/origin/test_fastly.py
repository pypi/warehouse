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

import pretend
import requests

from zope.interface.verify import verifyClass

from warehouse.cache.origin import fastly
from warehouse.cache.origin.interfaces import IOriginCache


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
        cacher.cache(["abc", "defg"], request, response, seconds=9123)

        assert response.headers == {
            "Surrogate-Key": "abc defg",
            "Surrogate-Control": "max-age=9123",
        }

    def test_purge(self, monkeypatch):
        cacher = fastly.FastlyCache(
            api_key="an api key",
            service_id="the-service-id",
        )

        response = pretend.stub(
            raise_for_status=pretend.call_recorder(lambda: None),
        )
        session_obj = pretend.stub(
            post=pretend.call_recorder(lambda *a, **kw: response),
            __enter__=lambda: session_obj,
            __exit__=lambda *a, **kw: None,
        )
        session_cls = pretend.call_recorder(lambda: session_obj)
        monkeypatch.setattr(requests, "session", session_cls)

        cacher.purge(["one", "two"])

        assert session_cls.calls == [pretend.call()]
        assert session_obj.post.calls == [
            pretend.call(
                "https://api.fastly.com/service/the-service-id/purge/one",
                headers={
                    "Accept": "application/json",
                    "Fastly-Key": "an api key",
                    "Fastly-Soft-Purge": "1",
                },
            ),
            pretend.call(
                "https://api.fastly.com/service/the-service-id/purge/two",
                headers={
                    "Accept": "application/json",
                    "Fastly-Key": "an api key",
                    "Fastly-Soft-Purge": "1",
                },
            ),
        ]
        assert response.raise_for_status.calls == [
            pretend.call(),
            pretend.call(),
        ]
