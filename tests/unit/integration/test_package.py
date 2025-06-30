# SPDX-License-Identifier: Apache-2.0

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
