# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from zope.interface.verify import verifyClass

from warehouse.metrics import services
from warehouse.metrics.interfaces import IMetricsService
from warehouse.metrics.services import DataDogMetrics, NullMetrics


class TestNullMetrics:
    def test_verify_service(self):
        assert verifyClass(IMetricsService, NullMetrics)

    def test_create_service(self):
        assert isinstance(
            NullMetrics.create_service(pretend.stub(), pretend.stub()), NullMetrics
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
    def test_noop(self, method):
        metrics = NullMetrics()
        getattr(metrics, method)("my metric", pretend.stub())

    def test_timed(self):
        metrics = NullMetrics()

        @metrics.timed("my metric")
        @pretend.call_recorder
        def fn(inp):
            return inp

        result = pretend.stub()
        assert fn(result) is result
        assert fn.calls == [pretend.call(result)]

        with metrics.timed("my metric"):
            pass

    def test_event(self):
        metrics = NullMetrics()
        metrics.event(pretend.stub(), pretend.stub(), pretend.stub())

    def test_service_check(self):
        metrics = NullMetrics()
        metrics.service_check(pretend.stub(), pretend.stub())


class TestDataDogMetrics:
    def test_verify_service(self):
        assert verifyClass(IMetricsService, DataDogMetrics)

    def test_create_service_defaults(self, monkeypatch):
        datadog_obj = pretend.stub()
        datadog_cls = pretend.call_recorder(lambda **kw: datadog_obj)

        monkeypatch.setattr(services, "DogStatsd", datadog_cls)

        context = pretend.stub()
        request = pretend.stub(registry=pretend.stub(settings={}))

        metrics = DataDogMetrics.create_service(context, request)

        assert metrics._datadog is datadog_obj
        assert datadog_cls.calls == [
            pretend.call(host="127.0.0.1", port=8125, namespace=None, use_ms=True)
        ]

    def test_create_service_overrides(self, monkeypatch):
        datadog_obj = pretend.stub()
        datadog_cls = pretend.call_recorder(lambda **kw: datadog_obj)

        monkeypatch.setattr(services, "DogStatsd", datadog_cls)

        context = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "metrics.host": "example.com",
                    "metrics.port": "9152",
                    "metrics.namespace": "thing",
                }
            )
        )

        metrics = DataDogMetrics.create_service(context, request)

        assert metrics._datadog is datadog_obj
        assert datadog_cls.calls == [
            pretend.call(host="example.com", port=9152, namespace="thing", use_ms=True)
        ]

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
    def test_dispatches_basic(self, method):
        method_fn = pretend.call_recorder(lambda *a, **kw: None)
        datadog = pretend.stub(**{method: method_fn})

        metrics = DataDogMetrics(datadog)
        getattr(metrics, method)("my metric", 3, tags=["foo", "bar"], sample_rate=0.5)

        assert method_fn.calls == [
            pretend.call("my metric", 3, tags=["foo", "bar"], sample_rate=0.5)
        ]

    def test_dispatches_timed(self):
        timer = pretend.stub()
        datadog = pretend.stub(timed=pretend.call_recorder(lambda *a, **k: timer))

        metrics = DataDogMetrics(datadog)

        assert (
            metrics.timed("thing.timed", tags=["wat"], sample_rate=0.4, use_ms=True)
            is timer
        )
        assert datadog.timed.calls == [
            pretend.call("thing.timed", tags=["wat"], sample_rate=0.4, use_ms=True)
        ]

    def test_dispatches_event(self):
        datadog = pretend.stub(event=pretend.call_recorder(lambda *a, **k: None))
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

        assert datadog.event.calls == [
            pretend.call(
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
        ]

    def test_dispatches_service_check(self):
        datadog = pretend.stub(
            service_check=pretend.call_recorder(lambda *a, **k: None)
        )
        metrics = DataDogMetrics(datadog)

        metrics.service_check(
            "name!",
            "ok",
            tags=["one", "two"],
            timestamp="now",
            hostname="example.com",
            message="my message",
        )

        assert datadog.service_check.calls == [
            pretend.call(
                "name!",
                "ok",
                tags=["one", "two"],
                timestamp="now",
                hostname="example.com",
                message="my message",
            )
        ]
