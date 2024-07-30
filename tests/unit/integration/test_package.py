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

import pytest

from warehouse import integrations


class TestCache:
    def test_set(self):
        cache = integrations.PublicKeysCache(cache_time=10)
        cache.set(now=1, value="foo")

        assert cache.cached_at == 1
        assert cache.cache == "foo"

    def test_get_no_cache(self):
        cache = integrations.PublicKeysCache(cache_time=10)

        with pytest.raises(integrations.CacheMissError):
            cache.get(now=1)

    def test_get_old_cache(self):
        cache = integrations.PublicKeysCache(cache_time=10)
        cache.set(now=5, value="foo")

        with pytest.raises(integrations.CacheMissError):
            cache.get(now=20)

    def test_get_valid(self):
        cache = integrations.PublicKeysCache(cache_time=10)
        cache.set(now=5, value="foo")

        assert cache.get(now=10) == "foo"


class TestPayloadVerifier:
    def test_unimplemented(self, metrics):
        cache = integrations.PublicKeysCache(cache_time=10)
        payload_verifier = integrations.PayloadVerifier(
            metrics=metrics, public_keys_cache=cache
        )

        with pytest.raises(NotImplementedError):
            payload_verifier.metric_name

        with pytest.raises(NotImplementedError):
            payload_verifier.retrieve_public_key_payload()

        with pytest.raises(NotImplementedError):
            payload_verifier.extract_public_keys({})
