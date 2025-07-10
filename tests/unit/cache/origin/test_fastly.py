# SPDX-License-Identifier: Apache-2.0

import time

from unittest.mock import Mock

import celery.exceptions
import forcediphttpsadapter.adapters
import pretend
import pytest
import requests

from zope.interface.verify import verifyClass

from warehouse.cache.origin import fastly
from warehouse.cache.origin.interfaces import IOriginCache
from warehouse.metrics.interfaces import IMetricsService


class TestPurgeKey:
    def test_purges_successfully(self, monkeypatch, metrics):
        task = pretend.stub()
        cacher = pretend.stub(
            purge_key=pretend.call_recorder(lambda k, metrics=None: None)
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(
                lambda svc, context=None, name=None: {
                    IOriginCache: cacher,
                    IMetricsService: metrics,
                }.get(svc)
            ),
            log=pretend.stub(info=pretend.call_recorder(lambda *args, **kwargs: None)),
        )

        fastly.purge_key(task, request, "foo")

        assert request.find_service.calls == [
            pretend.call(IOriginCache),
            pretend.call(IMetricsService, context=None),
        ]
        assert cacher.purge_key.calls == [pretend.call("foo", metrics=metrics)]
        assert request.log.info.calls == [pretend.call("Purging %s", "foo")]

    @pytest.mark.parametrize(
        "exception_type",
        [
            requests.ConnectionError,
            requests.HTTPError,
            requests.Timeout,
            fastly.UnsuccessfulPurgeError,
        ],
    )
    def test_purges_fails(self, monkeypatch, metrics, exception_type):
        exc = exception_type()

        class Cacher:
            @staticmethod
            @pretend.call_recorder
            def purge_key(key, metrics=None):
                raise exc

        class Task:
            @staticmethod
            @pretend.call_recorder
            def retry(exc):
                raise celery.exceptions.Retry

        task = Task()
        cacher = Cacher()
        request = pretend.stub(
            find_service=pretend.call_recorder(
                lambda svc, context=None, name=None: {
                    IOriginCache: cacher,
                    IMetricsService: metrics,
                }.get(svc)
            ),
            log=pretend.stub(
                info=pretend.call_recorder(lambda *args, **kwargs: None),
                error=pretend.call_recorder(lambda *args, **kwargs: None),
            ),
        )

        with pytest.raises(celery.exceptions.Retry):
            fastly.purge_key(task, request, "foo")

        assert request.find_service.calls == [
            pretend.call(IOriginCache),
            pretend.call(IMetricsService, context=None),
        ]
        assert cacher.purge_key.calls == [pretend.call("foo", metrics=metrics)]
        assert task.retry.calls == [pretend.call(exc=exc)]
        assert request.log.info.calls == [pretend.call("Purging %s", "foo")]
        assert request.log.error.calls == [
            pretend.call("Error purging %s: %s", "foo", str(exception_type()))
        ]


class TestFastlyCache:
    def test_verify_service(self):
        assert verifyClass(IOriginCache, fastly.FastlyCache)

    def test_create_service(self):
        purge_key = pretend.stub(delay=pretend.stub())
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "origin_cache.api_endpoint": "https://api.example.com",
                    "origin_cache.api_key": "the api key",
                    "origin_cache.service_id": "the service id",
                }
            ),
            task=lambda f: purge_key,
        )
        cacher = fastly.FastlyCache.create_service(None, request)
        assert isinstance(cacher, fastly.FastlyCache)
        assert cacher.api_endpoint == "https://api.example.com"
        assert cacher.api_connect_via is None
        assert cacher.api_key == "the api key"
        assert cacher.service_id == "the service id"
        assert cacher._purger is purge_key.delay

    def test_create_service_default_endpoint(self):
        purge_key = pretend.stub(delay=pretend.stub())
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "origin_cache.api_key": "the api key",
                    "origin_cache.service_id": "the service id",
                }
            ),
            task=lambda f: purge_key,
        )
        cacher = fastly.FastlyCache.create_service(None, request)
        assert isinstance(cacher, fastly.FastlyCache)
        assert cacher.api_endpoint == "https://api.fastly.com"
        assert cacher.api_connect_via is None
        assert cacher.api_key == "the api key"
        assert cacher.service_id == "the service id"
        assert cacher._purger is purge_key.delay

    def test_create_service_connect_via(self):
        purge_key = pretend.stub(delay=pretend.stub())
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "origin_cache.api_connect_via": "172.16.0.1",
                    "origin_cache.api_key": "the api key",
                    "origin_cache.service_id": "the service id",
                }
            ),
            task=lambda f: purge_key,
        )
        cacher = fastly.FastlyCache.create_service(None, request)
        assert isinstance(cacher, fastly.FastlyCache)
        assert cacher.api_endpoint == "https://api.fastly.com"
        assert cacher.api_connect_via == "172.16.0.1"
        assert cacher.api_key == "the api key"
        assert cacher.service_id == "the service id"
        assert cacher._purger is purge_key.delay

    def test_adds_surrogate_key(self):
        request = pretend.stub()
        response = pretend.stub(headers={})

        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key=None,
            service_id=None,
            purger=None,
        )
        cacher.cache(["abc", "defg"], request, response)

        assert response.headers == {"Surrogate-Key": "abc defg"}

    def test_adds_surrogate_control(self):
        request = pretend.stub()
        response = pretend.stub(headers={})

        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key=None,
            service_id=None,
            purger=None,
        )
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
                "max-age=9123, stale-while-revalidate=4567, stale-if-error=2276"
            ),
        }

    def test_override_ttl_on_response(self):
        request = pretend.stub()
        response = pretend.stub(headers={}, override_ttl=6969)

        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key=None,
            service_id=None,
            purger=None,
        )
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
                "max-age=6969, stale-while-revalidate=4567, stale-if-error=2276"
            ),
        }

    def test_multiple_calls_to_cache_dont_overwrite_surrogate_keys(self):
        request = pretend.stub()
        response = pretend.stub(headers={})

        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key=None,
            service_id=None,
            purger=None,
        )
        cacher.cache(["abc"], request, response)
        cacher.cache(["defg"], request, response)

        assert response.headers == {"Surrogate-Key": "abc defg"}

    def test_multiple_calls_with_different_requests(self):
        request_a = pretend.stub()
        request_b = pretend.stub()
        response_a = pretend.stub(headers={})
        response_b = pretend.stub(headers={})

        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key=None,
            service_id=None,
            purger=None,
        )
        cacher.cache(["abc"], request_a, response_a)
        cacher.cache(["defg"], request_b, response_b)

        assert response_a.headers == {"Surrogate-Key": "abc"}
        assert response_b.headers == {"Surrogate-Key": "defg"}

    def test_purge(self, monkeypatch):
        purge_delay = pretend.call_recorder(lambda *a, **kw: None)
        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key="an api key",
            service_id="the-service-id",
            purger=purge_delay,
        )

        cacher.purge(["one", "two"])

        assert purge_delay.calls == [pretend.call("one"), pretend.call("two")]

    @pytest.mark.parametrize(
        ("connect_via", "forced_ip_https_adapter_calls"),
        [(None, []), ("172.16.0.1", [pretend.call(dest_ip="172.16.0.1")])],
    )
    def test__purge_key_ok(
        self, monkeypatch, connect_via, forced_ip_https_adapter_calls
    ):
        forced_ip_https_adapter = pretend.call_recorder(lambda *a, **kw: None)

        class MockForcedIPHTTPSAdapter:
            def __init__(self, *a, **kw):
                return forced_ip_https_adapter(*a, **kw)

        monkeypatch.setattr(
            forcediphttpsadapter.adapters,
            "ForcedIPHTTPSAdapter",
            MockForcedIPHTTPSAdapter,
        )

        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        requests_mount = pretend.call_recorder(lambda *a, **kw: None)
        response = pretend.stub(
            raise_for_status=pretend.call_recorder(lambda: None),
            json=lambda: {"status": "ok"},
        )
        requests_post = pretend.call_recorder(lambda *a, **kw: response)

        def requests_session(*a, **kw):
            return pretend.stub(
                mount=requests_mount,
                post=requests_post,
            )

        monkeypatch.setattr(requests, "Session", requests_session)

        cacher._purge_key("one", connect_via=connect_via)

        assert forced_ip_https_adapter.calls == forced_ip_https_adapter_calls
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

    @pytest.mark.parametrize(
        ("connect_via", "forced_ip_https_adapter_calls", "result"),
        [
            (None, [], {"status": "fail"}),
            (None, [], {}),
            ("172.16.0.1", [pretend.call(dest_ip="172.16.0.1")], {"status": "fail"}),
            ("172.16.0.1", [pretend.call(dest_ip="172.16.0.1")], {}),
        ],
    )
    def test__purge_key_unsuccessful(
        self, monkeypatch, connect_via, forced_ip_https_adapter_calls, result
    ):
        forced_ip_https_adapter = pretend.call_recorder(lambda *a, **kw: None)

        class MockForcedIPHTTPSAdapter:
            def __init__(self, *a, **kw):
                return forced_ip_https_adapter(*a, **kw)

        monkeypatch.setattr(
            forcediphttpsadapter.adapters,
            "ForcedIPHTTPSAdapter",
            MockForcedIPHTTPSAdapter,
        )

        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        requests_mount = pretend.call_recorder(lambda *a, **kw: None)
        response = pretend.stub(
            raise_for_status=pretend.call_recorder(lambda: None), json=lambda: result
        )
        requests_post = pretend.call_recorder(lambda *a, **kw: response)

        def requests_session(*a, **kw):
            return pretend.stub(
                mount=requests_mount,
                post=requests_post,
            )

        monkeypatch.setattr(requests, "Session", requests_session)

        with pytest.raises(fastly.UnsuccessfulPurgeError):
            cacher._purge_key("one", connect_via=connect_via)

        assert forced_ip_https_adapter.calls == forced_ip_https_adapter_calls
        assert requests_post.calls == [
            pretend.call(
                "https://api.fastly.com/service/the-service-id/purge/one",
                headers={
                    "Accept": "application/json",
                    "Fastly-Key": "an api key",
                    "Fastly-Soft-Purge": "1",
                },
            )
        ]
        assert response.raise_for_status.calls == [pretend.call()]

    @pytest.mark.parametrize(
        ("connect_via", "purge_key_calls"),
        [
            (
                None,
                [
                    pretend.call("one", connect_via=None),
                    pretend.call("one", connect_via=None),
                ],
            ),
            (
                "172.16.0.1",
                [
                    pretend.call("one", connect_via="172.16.0.1"),
                    pretend.call("one", connect_via="172.16.0.1"),
                ],
            ),
        ],
    )
    def test__double_purge_key_ok(self, monkeypatch, connect_via, purge_key_calls):
        monkeypatch.setattr(time, "sleep", lambda x: None)
        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        cacher._purge_key = pretend.call_recorder(lambda *a, **kw: None)

        cacher._double_purge_key("one", connect_via=connect_via)

        assert cacher._purge_key.calls == purge_key_calls

    @pytest.mark.parametrize(
        ("connect_via", "purge_key_calls"),
        [
            (
                None,
                [
                    pretend.call("one", connect_via=None),
                ],
            ),
            (
                "172.16.0.1",
                [
                    pretend.call("one", connect_via="172.16.0.1"),
                ],
            ),
        ],
    )
    def test__double_purge_key_unsuccessful_first(
        self, monkeypatch, connect_via, purge_key_calls
    ):
        monkeypatch.setattr(time, "sleep", lambda x: None)
        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        cacher._purge_key = pretend.call_recorder(
            pretend.raiser(fastly.UnsuccessfulPurgeError)
        )

        with pytest.raises(fastly.UnsuccessfulPurgeError):
            cacher._double_purge_key("one", connect_via=connect_via)

        assert cacher._purge_key.calls == purge_key_calls

    @pytest.mark.parametrize(
        ("connect_via", "purge_key_calls"),
        [
            (
                None,
                [
                    pretend.call("one", connect_via=None),
                    pretend.call("one", connect_via=None),
                ],
            ),
            (
                "172.16.0.1",
                [
                    pretend.call("one", connect_via="172.16.0.1"),
                    pretend.call("one", connect_via="172.16.0.1"),
                ],
            ),
        ],
    )
    def test__double_purge_key_unsuccessful_second(
        self, monkeypatch, connect_via, purge_key_calls
    ):
        monkeypatch.setattr(time, "sleep", lambda x: None)
        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        _purge_key_mock = Mock()
        _purge_key_mock.side_effect = [None, fastly.UnsuccessfulPurgeError]
        cacher._purge_key = pretend.call_recorder(_purge_key_mock)

        with pytest.raises(fastly.UnsuccessfulPurgeError):
            cacher._double_purge_key("one", connect_via=connect_via)

        assert cacher._purge_key.calls == purge_key_calls

    @pytest.mark.parametrize(
        ("connect_via", "purge_key_mock_effects", "purge_key_calls", "metrics_calls"),
        [
            (
                "172.16.0.1",
                [requests.ConnectionError, None, None],
                [
                    pretend.call("one", connect_via="172.16.0.1"),
                    pretend.call("one", connect_via=None),
                    pretend.call("one", connect_via=None),
                ],
                [
                    pretend.call(
                        "warehouse.cache.origin.fastly.connect_via.failed",
                        tags=["ip_address:172.16.0.1"],
                    )
                ],
            ),
            (
                "172.16.0.1",
                [requests.exceptions.SSLError, None, None],
                [
                    pretend.call("one", connect_via="172.16.0.1"),
                    pretend.call("one", connect_via=None),
                    pretend.call("one", connect_via=None),
                ],
                [
                    pretend.call(
                        "warehouse.cache.origin.fastly.connect_via.failed",
                        tags=["ip_address:172.16.0.1"],
                    )
                ],
            ),
        ],
    )
    def test_purge_key_fallback(
        self,
        monkeypatch,
        metrics,
        connect_via,
        purge_key_mock_effects,
        purge_key_calls,
        metrics_calls,
    ):
        monkeypatch.setattr(time, "sleep", lambda x: None)
        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        _purge_key_mock = Mock()
        _purge_key_mock.side_effect = purge_key_mock_effects
        cacher._purge_key = pretend.call_recorder(_purge_key_mock)

        cacher.purge_key("one", metrics=metrics)

        assert cacher._purge_key.calls == purge_key_calls
        assert metrics.increment.calls == metrics_calls

    @pytest.mark.parametrize(
        (
            "connect_via",
            "purge_key_mock_effects",
            "expected_raise",
            "purge_key_calls",
        ),
        [
            (
                None,
                [requests.ConnectionError, None, None],
                requests.ConnectionError,
                [pretend.call("one", connect_via=None)],
            ),
            (
                None,
                [requests.exceptions.SSLError, None, None],
                requests.exceptions.SSLError,
                [pretend.call("one", connect_via=None)],
            ),
            (
                None,
                [fastly.UnsuccessfulPurgeError, None, None],
                fastly.UnsuccessfulPurgeError,
                [pretend.call("one", connect_via=None)],
            ),
            (
                "172.16.0.1",
                [fastly.UnsuccessfulPurgeError, None, None],
                fastly.UnsuccessfulPurgeError,
                [pretend.call("one", connect_via="172.16.0.1")],
            ),
        ],
    )
    def test_purge_key_no_fallback(
        self,
        monkeypatch,
        metrics,
        connect_via,
        purge_key_mock_effects,
        expected_raise,
        purge_key_calls,
    ):
        monkeypatch.setattr(time, "sleep", lambda x: None)
        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        _purge_key_mock = Mock()
        _purge_key_mock.side_effect = purge_key_mock_effects
        cacher._purge_key = pretend.call_recorder(_purge_key_mock)

        with pytest.raises(expected_raise):
            cacher.purge_key("one", metrics=metrics)

        assert cacher._purge_key.calls == purge_key_calls
        assert metrics.increment.calls == []


class TestNullFastlyCache:
    def test_purge_key_prints(self, capsys, metrics):
        purge_key = pretend.stub(delay=pretend.stub())
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "origin_cache.api_endpoint": "https://api.example.com",
                    "origin_cache.api_key": "the api key",
                    "origin_cache.service_id": "the service id",
                }
            ),
            task=lambda f: purge_key,
        )
        cacher = fastly.NullFastlyCache.create_service(None, request)
        cacher.purge_key("one", metrics=metrics)

        captured = capsys.readouterr()
        expected = """
Origin cache purge issued:
* URL: 'https://api.example.com/service/the service id/purge/one'
* Headers: {'Accept': 'application/json', 'Fastly-Key': 'the api key', 'Fastly-Soft-Purge': '1'}
"""  # noqa
        assert captured.out.strip() == expected.strip()
