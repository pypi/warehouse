# SPDX-License-Identifier: Apache-2.0

import types

import pytest

from zope.interface.verify import verifyClass

from warehouse.metrics import services
from warehouse.metrics.interfaces import IMetricsService
from warehouse.metrics.services import DataDogMetrics, NullMetrics


class TestNullMetrics:
    def test_verify_service(self):
        assert verifyClass(IMetricsService, NullMetrics)

    def test_create_service(self, mocker):
        service = NullMetrics.create_service(
            mocker.sentinel.context, mocker.sentinel.request
        )
        assert isinstance(service, NullMetrics)

    @pytest.mark.parametrize(
        "method",
        [
            "gauge",
            "increment",
            "decrement",
            "histogram",
            "distribution",
            "timing",
            "set",
        ],
    )
    def test_noop(self, method, mocker):
        metrics = NullMetrics()
        getattr(metrics, method)("my metric", mocker.sentinel.value)

    def test_timed(self, mocker):
        metrics = NullMetrics()

        fn = mocker.stub()
        fn.side_effect = lambda inp: inp
        decorated = metrics.timed("my metric")(fn)

        result = mocker.sentinel.result
        assert decorated(result) is result
        fn.assert_called_once_with(result)

        with metrics.timed("my metric"):
            pass

    def test_event(self, mocker):
        metrics = NullMetrics()
        metrics.event(
            mocker.sentinel.title, mocker.sentinel.text, mocker.sentinel.alert_type
        )

    def test_service_check(self, mocker):
        metrics = NullMetrics()
        metrics.service_check(mocker.sentinel.check_name, mocker.sentinel.status)


class TestDataDogMetrics:
    def test_verify_service(self):
        assert verifyClass(IMetricsService, DataDogMetrics)

    def test_create_service_defaults(self, mocker):
        datadog_cls = mocker.patch.object(services, "DogStatsd", autospec=True)

        request = types.SimpleNamespace(registry=types.SimpleNamespace(settings={}))

        metrics = DataDogMetrics.create_service(mocker.sentinel.context, request)

        assert metrics._datadog is datadog_cls.return_value
        datadog_cls.assert_called_once_with(
            host="192.0.2.1", port=8125, namespace=None, use_ms=True
        )

    def test_create_service_overrides(self, mocker):
        datadog_cls = mocker.patch.object(services, "DogStatsd", autospec=True)

        request = types.SimpleNamespace(
            registry=types.SimpleNamespace(
                settings={
                    "metrics.host": "example.com",
                    "metrics.port": "9152",
                    "metrics.namespace": "thing",
                }
            )
        )

        metrics = DataDogMetrics.create_service(mocker.sentinel.context, request)

        assert metrics._datadog is datadog_cls.return_value
        datadog_cls.assert_called_once_with(
            host="example.com", port=9152, namespace="thing", use_ms=True
        )

    @pytest.mark.parametrize(
        "method",
        [
            "gauge",
            "increment",
            "decrement",
            "histogram",
            "distribution",
            "timing",
            "set",
        ],
    )
    def test_dispatches_basic(self, method, mocker):
        datadog = mocker.create_autospec(services.DogStatsd, instance=True)

        metrics = DataDogMetrics(datadog)
        getattr(metrics, method)("my metric", 3, tags=["foo", "bar"], sample_rate=0.5)

        getattr(datadog, method).assert_called_once_with(
            "my metric", 3, tags=["foo", "bar"], sample_rate=0.5
        )

    def test_dispatches_timed(self, mocker):
        datadog = mocker.create_autospec(services.DogStatsd, instance=True)
        datadog.timed.return_value = mocker.sentinel.timer

        metrics = DataDogMetrics(datadog)

        assert (
            metrics.timed("thing.timed", tags=["wat"], sample_rate=0.4, use_ms=True)
            is mocker.sentinel.timer
        )
        datadog.timed.assert_called_once_with(
            "thing.timed", tags=["wat"], sample_rate=0.4, use_ms=True
        )

    def test_dispatches_event(self, mocker):
        datadog = mocker.create_autospec(services.DogStatsd, instance=True)
        metrics = DataDogMetrics(datadog)

        metrics.event(
            "my title",
            "this is text",
            alert_type="thing",
            aggregation_key="wat",
            source_type_name="ok?",
            date_happened="now?",
            priority="who knows",
            tags=["one", "two"],
            hostname="example.com",
        )

        datadog.event.assert_called_once_with(
            "my title",
            "this is text",
            alert_type="thing",
            aggregation_key="wat",
            source_type_name="ok?",
            date_happened="now?",
            priority="who knows",
            tags=["one", "two"],
            hostname="example.com",
        )

    def test_dispatches_service_check(self, mocker):
        datadog = mocker.create_autospec(services.DogStatsd, instance=True)
        metrics = DataDogMetrics(datadog)

        metrics.service_check(
            "name!",
            "ok",
            tags=["one", "two"],
            timestamp="now",
            hostname="example.com",
            message="my message",
        )

        datadog.service_check.assert_called_once_with(
            "name!",
            "ok",
            tags=["one", "two"],
            timestamp="now",
            hostname="example.com",
            message="my message",
        )
