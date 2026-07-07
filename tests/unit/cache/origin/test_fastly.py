# SPDX-License-Identifier: Apache-2.0

import types

from unittest.mock import call

import celery.exceptions
import forcediphttpsadapter.adapters
import pytest
import requests

from zope.interface.verify import verifyClass

from warehouse.cache.origin import fastly
from warehouse.cache.origin.interfaces import IOriginCache
from warehouse.metrics.interfaces import IMetricsService


class TestPurgeKey:
    def test_purges_successfully(self, pyramid_request, mocker, metrics):
        cacher = mocker.Mock(spec=["purge_key"])
        find_service = mocker.patch.object(
            pyramid_request,
            "find_service",
            side_effect=lambda svc, context=None, name=None: {
                IOriginCache: cacher,
                IMetricsService: metrics,
            }.get(svc),
        )

        fastly.purge_key(mocker.sentinel.task, pyramid_request, "foo")

        assert find_service.call_args_list == [
            call(IOriginCache),
            call(IMetricsService, context=None),
        ]
        cacher.purge_key.assert_called_once_with("foo", metrics=metrics)
        pyramid_request.log.info.assert_called_once_with("Purging %s", "foo")

    @pytest.mark.parametrize(
        "exception_type",
        [
            requests.ConnectionError,
            requests.HTTPError,
            requests.Timeout,
            fastly.UnsuccessfulPurgeError,
        ],
    )
    def test_purges_fails(self, pyramid_request, mocker, metrics, exception_type):
        exc = exception_type()

        cacher = mocker.Mock(spec=["purge_key"])
        cacher.purge_key.side_effect = exc
        task = mocker.Mock(spec=["retry"])
        task.retry.side_effect = celery.exceptions.Retry
        find_service = mocker.patch.object(
            pyramid_request,
            "find_service",
            side_effect=lambda svc, context=None, name=None: {
                IOriginCache: cacher,
                IMetricsService: metrics,
            }.get(svc),
        )

        with pytest.raises(celery.exceptions.Retry):
            fastly.purge_key(task, pyramid_request, "foo")

        assert find_service.call_args_list == [
            call(IOriginCache),
            call(IMetricsService, context=None),
        ]
        cacher.purge_key.assert_called_once_with("foo", metrics=metrics)
        task.retry.assert_called_once_with(exc=exc)
        pyramid_request.log.info.assert_called_once_with("Purging %s", "foo")
        pyramid_request.log.error.assert_called_once_with(
            "Error purging %s: %s", "foo", str(exc)
        )


class TestFastlyCache:
    def test_verify_service(self):
        assert verifyClass(IOriginCache, fastly.FastlyCache)

    def test_create_service(self, pyramid_request, mocker):
        task = mocker.Mock(spec=["delay"])
        mocker.patch.object(pyramid_request, "task", return_value=task)
        pyramid_request.registry.settings.update(
            {
                "origin_cache.api_endpoint": "https://api.example.com",
                "origin_cache.api_key": "the api key",
                "origin_cache.service_id": "the service id",
            }
        )
        cacher = fastly.FastlyCache.create_service(None, pyramid_request)
        assert isinstance(cacher, fastly.FastlyCache)
        assert cacher.api_endpoint == "https://api.example.com"
        assert cacher.api_connect_via is None
        assert cacher.api_key == "the api key"
        assert cacher.service_id == "the service id"
        assert cacher._purger is task.delay
        pyramid_request.task.assert_called_once_with(fastly.purge_key)

    def test_create_service_default_endpoint(self, pyramid_request, mocker):
        task = mocker.Mock(spec=["delay"])
        mocker.patch.object(pyramid_request, "task", return_value=task)
        pyramid_request.registry.settings.update(
            {
                "origin_cache.api_key": "the api key",
                "origin_cache.service_id": "the service id",
            }
        )
        cacher = fastly.FastlyCache.create_service(None, pyramid_request)
        assert isinstance(cacher, fastly.FastlyCache)
        assert cacher.api_endpoint == "https://api.fastly.com"
        assert cacher.api_connect_via is None
        assert cacher.api_key == "the api key"
        assert cacher.service_id == "the service id"
        assert cacher._purger is task.delay

    def test_create_service_connect_via(self, pyramid_request, mocker):
        task = mocker.Mock(spec=["delay"])
        mocker.patch.object(pyramid_request, "task", return_value=task)
        pyramid_request.registry.settings.update(
            {
                "origin_cache.api_connect_via": "172.16.0.1",
                "origin_cache.api_key": "the api key",
                "origin_cache.service_id": "the service id",
            }
        )
        cacher = fastly.FastlyCache.create_service(None, pyramid_request)
        assert isinstance(cacher, fastly.FastlyCache)
        assert cacher.api_endpoint == "https://api.fastly.com"
        assert cacher.api_connect_via == "172.16.0.1"
        assert cacher.api_key == "the api key"
        assert cacher.service_id == "the service id"
        assert cacher._purger is task.delay

    def test_adds_surrogate_key(self, mocker):
        response = types.SimpleNamespace(headers={})

        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key=None,
            service_id=None,
            purger=None,
        )
        cacher.cache(["abc", "defg"], mocker.sentinel.request, response)

        assert response.headers == {"Surrogate-Key": "abc defg"}

    def test_adds_surrogate_control(self, mocker):
        response = types.SimpleNamespace(headers={})

        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key=None,
            service_id=None,
            purger=None,
        )
        cacher.cache(
            ["abc", "defg"],
            mocker.sentinel.request,
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

    def test_override_ttl_on_response(self, mocker):
        response = types.SimpleNamespace(headers={}, override_ttl=6969)

        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key=None,
            service_id=None,
            purger=None,
        )
        cacher.cache(
            ["abc", "defg"],
            mocker.sentinel.request,
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

    def test_multiple_calls_to_cache_dont_overwrite_surrogate_keys(self, mocker):
        response = types.SimpleNamespace(headers={})

        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key=None,
            service_id=None,
            purger=None,
        )
        cacher.cache(["abc"], mocker.sentinel.request, response)
        cacher.cache(["defg"], mocker.sentinel.request, response)

        assert response.headers == {"Surrogate-Key": "abc defg"}

    def test_multiple_calls_with_different_requests(self, mocker):
        response_a = types.SimpleNamespace(headers={})
        response_b = types.SimpleNamespace(headers={})

        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key=None,
            service_id=None,
            purger=None,
        )
        cacher.cache(["abc"], mocker.sentinel.request_a, response_a)
        cacher.cache(["defg"], mocker.sentinel.request_b, response_b)

        assert response_a.headers == {"Surrogate-Key": "abc"}
        assert response_b.headers == {"Surrogate-Key": "defg"}

    def test_purge(self, mocker):
        purge_delay = mocker.Mock()
        cacher = fastly.FastlyCache(
            api_endpoint=None,
            api_connect_via=None,
            api_key="an api key",
            service_id="the-service-id",
            purger=purge_delay,
        )

        cacher.purge(["one", "two"])

        assert purge_delay.call_args_list == [call("one"), call("two")]

    @pytest.mark.parametrize(
        ("connect_via", "forced_ip_https_adapter_calls"),
        [(None, []), ("172.16.0.1", [call(dest_ip="172.16.0.1")])],
    )
    def test__purge_key_ok(self, mocker, connect_via, forced_ip_https_adapter_calls):
        # The adapter is mocked to assert it's constructed with the right
        # dest_ip; that intercept rules out `responses` here, since a mounted
        # mock adapter would shadow its transport patch.
        forced_ip_https_adapter = mocker.patch.object(
            forcediphttpsadapter.adapters, "ForcedIPHTTPSAdapter", autospec=True
        )

        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        response = mocker.Mock(spec=["raise_for_status", "json"])
        response.json.return_value = {"status": "ok"}
        session_cls = mocker.patch.object(requests, "Session", autospec=True)
        session_cls.return_value.post.return_value = response

        cacher._purge_key("one", connect_via=connect_via)

        assert forced_ip_https_adapter.call_args_list == forced_ip_https_adapter_calls
        session_cls.return_value.post.assert_called_once_with(
            "https://api.fastly.com/service/the-service-id/purge/one",
            headers={
                "Accept": "application/json",
                "Fastly-Key": "an api key",
                "Fastly-Soft-Purge": "1",
            },
        )
        response.raise_for_status.assert_called_once_with()

    @pytest.mark.parametrize(
        ("connect_via", "forced_ip_https_adapter_calls", "result"),
        [
            (None, [], {"status": "fail"}),
            (None, [], {}),
            ("172.16.0.1", [call(dest_ip="172.16.0.1")], {"status": "fail"}),
            ("172.16.0.1", [call(dest_ip="172.16.0.1")], {}),
        ],
    )
    def test__purge_key_unsuccessful(
        self, mocker, connect_via, forced_ip_https_adapter_calls, result
    ):
        forced_ip_https_adapter = mocker.patch.object(
            forcediphttpsadapter.adapters, "ForcedIPHTTPSAdapter", autospec=True
        )

        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        response = mocker.Mock(spec=["raise_for_status", "json"])
        response.json.return_value = result
        session_cls = mocker.patch.object(requests, "Session", autospec=True)
        session_cls.return_value.post.return_value = response

        with pytest.raises(fastly.UnsuccessfulPurgeError):
            cacher._purge_key("one", connect_via=connect_via)

        assert forced_ip_https_adapter.call_args_list == forced_ip_https_adapter_calls
        session_cls.return_value.post.assert_called_once_with(
            "https://api.fastly.com/service/the-service-id/purge/one",
            headers={
                "Accept": "application/json",
                "Fastly-Key": "an api key",
                "Fastly-Soft-Purge": "1",
            },
        )
        response.raise_for_status.assert_called_once_with()

    @pytest.mark.parametrize(
        ("connect_via", "purge_key_calls"),
        [
            (
                None,
                [
                    call("one", connect_via=None),
                    call("one", connect_via=None),
                ],
            ),
            (
                "172.16.0.1",
                [
                    call("one", connect_via="172.16.0.1"),
                    call("one", connect_via="172.16.0.1"),
                ],
            ),
        ],
    )
    def test__double_purge_key_ok(self, mocker, connect_via, purge_key_calls):
        mocker.patch("time.sleep")
        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        cacher._purge_key = mocker.Mock()

        cacher._double_purge_key("one", connect_via=connect_via)

        assert cacher._purge_key.call_args_list == purge_key_calls

    @pytest.mark.parametrize(
        ("connect_via", "purge_key_calls"),
        [
            (
                None,
                [
                    call("one", connect_via=None),
                ],
            ),
            (
                "172.16.0.1",
                [
                    call("one", connect_via="172.16.0.1"),
                ],
            ),
        ],
    )
    def test__double_purge_key_unsuccessful_first(
        self, mocker, connect_via, purge_key_calls
    ):
        mocker.patch("time.sleep")
        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        cacher._purge_key = mocker.Mock(side_effect=fastly.UnsuccessfulPurgeError)

        with pytest.raises(fastly.UnsuccessfulPurgeError):
            cacher._double_purge_key("one", connect_via=connect_via)

        assert cacher._purge_key.call_args_list == purge_key_calls

    @pytest.mark.parametrize(
        ("connect_via", "purge_key_calls"),
        [
            (
                None,
                [
                    call("one", connect_via=None),
                    call("one", connect_via=None),
                ],
            ),
            (
                "172.16.0.1",
                [
                    call("one", connect_via="172.16.0.1"),
                    call("one", connect_via="172.16.0.1"),
                ],
            ),
        ],
    )
    def test__double_purge_key_unsuccessful_second(
        self, mocker, connect_via, purge_key_calls
    ):
        mocker.patch("time.sleep")
        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        cacher._purge_key = mocker.Mock(
            side_effect=[None, fastly.UnsuccessfulPurgeError]
        )

        with pytest.raises(fastly.UnsuccessfulPurgeError):
            cacher._double_purge_key("one", connect_via=connect_via)

        assert cacher._purge_key.call_args_list == purge_key_calls

    @pytest.mark.parametrize(
        ("connect_via", "purge_key_mock_effects", "purge_key_calls", "metrics_calls"),
        [
            (
                "172.16.0.1",
                [requests.ConnectionError, None, None],
                [
                    call("one", connect_via="172.16.0.1"),
                    call("one", connect_via=None),
                    call("one", connect_via=None),
                ],
                [
                    call(
                        "warehouse.cache.origin.fastly.connect_via.failed",
                        tags=["ip_address:172.16.0.1"],
                    )
                ],
            ),
            (
                "172.16.0.1",
                [requests.exceptions.SSLError, None, None],
                [
                    call("one", connect_via="172.16.0.1"),
                    call("one", connect_via=None),
                    call("one", connect_via=None),
                ],
                [
                    call(
                        "warehouse.cache.origin.fastly.connect_via.failed",
                        tags=["ip_address:172.16.0.1"],
                    )
                ],
            ),
        ],
    )
    def test_purge_key_fallback(
        self,
        mocker,
        metrics,
        connect_via,
        purge_key_mock_effects,
        purge_key_calls,
        metrics_calls,
    ):
        mocker.patch("time.sleep")
        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        cacher._purge_key = mocker.Mock(side_effect=purge_key_mock_effects)

        cacher.purge_key("one", metrics=metrics)

        assert cacher._purge_key.call_args_list == purge_key_calls
        assert metrics.increment.call_args_list == metrics_calls

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
                [call("one", connect_via=None)],
            ),
            (
                None,
                [requests.exceptions.SSLError, None, None],
                requests.exceptions.SSLError,
                [call("one", connect_via=None)],
            ),
            (
                None,
                [fastly.UnsuccessfulPurgeError, None, None],
                fastly.UnsuccessfulPurgeError,
                [call("one", connect_via=None)],
            ),
            (
                "172.16.0.1",
                [fastly.UnsuccessfulPurgeError, None, None],
                fastly.UnsuccessfulPurgeError,
                [call("one", connect_via="172.16.0.1")],
            ),
        ],
    )
    def test_purge_key_no_fallback(
        self,
        mocker,
        metrics,
        connect_via,
        purge_key_mock_effects,
        expected_raise,
        purge_key_calls,
    ):
        mocker.patch("time.sleep")
        cacher = fastly.FastlyCache(
            api_endpoint="https://api.fastly.com",
            api_connect_via=connect_via,
            api_key="an api key",
            service_id="the-service-id",
            purger=None,
        )

        cacher._purge_key = mocker.Mock(side_effect=purge_key_mock_effects)

        with pytest.raises(expected_raise):
            cacher.purge_key("one", metrics=metrics)

        assert cacher._purge_key.call_args_list == purge_key_calls
        metrics.increment.assert_not_called()


class TestNullFastlyCache:
    def test_purge_key_prints(self, pyramid_request, mocker, capsys, metrics):
        task = mocker.Mock(spec=["delay"])
        mocker.patch.object(pyramid_request, "task", return_value=task)
        pyramid_request.registry.settings.update(
            {
                "origin_cache.api_endpoint": "https://api.example.com",
                "origin_cache.api_key": "the api key",
                "origin_cache.service_id": "the service id",
            }
        )
        cacher = fastly.NullFastlyCache.create_service(None, pyramid_request)
        cacher.purge_key("one", metrics=metrics)

        captured = capsys.readouterr()
        expected = """
Origin cache purge issued:
* URL: 'https://api.example.com/service/the service id/purge/one'
* Headers: {'Accept': 'application/json', 'Fastly-Key': 'the api key', 'Fastly-Soft-Purge': '1'}
"""  # noqa: E501
        assert captured.out.strip() == expected.strip()
