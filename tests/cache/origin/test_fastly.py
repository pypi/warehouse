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
import pytest

from zope.interface.verify import verifyClass

from warehouse.cache.origin import fastly
from warehouse.cache.origin.interfaces import IOriginCache


class TestFastlyCache:

    def test_verify_service(self):
        assert verifyClass(IOriginCache, fastly.FastlyCache)

    def test_adds_surrogate_key(self):
        request = pretend.stub()
        response = pretend.stub(headers={})

        cacher = fastly.FastlyCache()
        cacher.cache(["abc", "defg"], request, response)

        assert response.headers == {"Surrogate-Key": "abc defg"}

    def test_adds_surrogate_control(self):
        request = pretend.stub()
        response = pretend.stub(headers={})

        cacher = fastly.FastlyCache()
        cacher.cache(["abc", "defg"], request, response, seconds=9123)

        assert response.headers == {
            "Surrogate-Key": "abc defg",
            "Surrogate-Control": "max-age=9123",
        }

    def test_purge_not_implemented(self):
        cacher = fastly.FastlyCache()

        with pytest.raises(NotImplementedError):
            cacher.purge(["one", "two"])


def test_includeme(monkeypatch):
    fastly_cache_obj = pretend.stub()
    fastly_cache_cls = pretend.call_recorder(lambda: fastly_cache_obj)
    monkeypatch.setattr(fastly, "FastlyCache", fastly_cache_cls)

    config = pretend.stub(
        include=pretend.call_recorder(lambda inc: None),
        register_service=pretend.call_recorder(lambda svc, iface: None),
    )

    fastly.includeme(config)

    assert config.include.calls == [pretend.call("pyramid_services")]
    assert config.register_service.calls == [
        pretend.call(fastly_cache_obj, IOriginCache),
    ]
    assert fastly_cache_cls.calls == [pretend.call()]
