# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest
import sentry_sdk

from sentry_sdk.integrations.wsgi import SentryWsgiMiddleware

from warehouse import sentry


def test_sentry_request_method():
    sentry_sdk = pretend.stub()
    request = pretend.stub(registry={"sentry": sentry_sdk}, sentry=sentry)

    assert sentry._sentry(request) is sentry_sdk


class TestSentryBeforeSend:

    @pytest.mark.parametrize(
        ("event", "hint"),
        [
            (
                {"message": "This is fine."},
                {"exc_info": (SystemExit, SystemExit(), "tracebk")},
            ),
            (
                {"message": "Worker (pid:35) was sent SIGINT!"},
                {},
            ),
            (
                {"message": "Worker (pid:1706) was sent code 131!"},
                {},
            ),
        ],
    )
    def test_ignore_exception(self, event, hint):
        assert sentry.before_send(event, hint) is None

    @pytest.mark.parametrize(
        ("event", "hint"),
        [
            (
                {"message": "This is fine."},
                {"exc_info": (ConnectionError, ConnectionError(), "tracebk")},
            ),
            ({"message": "This is fine."}, {"event_info": "This is a random event."}),
        ],
    )
    def test_report_event(self, event, hint):
        assert sentry.before_send(event, hint) is event


def test_includeme(monkeypatch):
    class Registry(dict):
        def __init__(self):
            self.settings = {}

    init_obj = pretend.call_recorder(lambda *a, **kw: "1")
    pyramid_obj = pretend.call_recorder(lambda *a, **kw: "2")
    celery_obj = pretend.call_recorder(lambda *a, **kw: "3")
    sql_obj = pretend.call_recorder(lambda *a, **kw: "4")
    log_obj = pretend.call_recorder(lambda *a, **kw: "5")
    monkeypatch.setattr(sentry_sdk, "init", init_obj)
    monkeypatch.setattr("warehouse.sentry.PyramidIntegration", pyramid_obj)
    monkeypatch.setattr("warehouse.sentry.CeleryIntegration", celery_obj)
    monkeypatch.setattr("warehouse.sentry.SqlalchemyIntegration", sql_obj)
    monkeypatch.setattr("warehouse.sentry.LoggingIntegration", log_obj)

    config = pretend.stub(
        registry=Registry(),
        add_request_method=pretend.call_recorder(lambda *a, **kw: None),
        add_wsgi_middleware=pretend.call_recorder(lambda *a, **kw: None),
    )
    config.registry.settings.update(
        {
            "warehouse.commit": "rand3rfgkn3424",
            "sentry.dsn": "test_dsn",
            "sentry.transport": "proxy_transport",
        }
    )

    sentry.includeme(config)

    assert init_obj.calls == [
        pretend.call(
            dsn="test_dsn",
            release="rand3rfgkn3424",
            transport="proxy_transport",
            before_send=sentry.before_send,
            attach_stacktrace=True,
            integrations=["2", "3", "4", "5"],
        )
    ]
    assert pyramid_obj.calls == [pretend.call()]
    assert celery_obj.calls == [pretend.call()]
    assert sql_obj.calls == [pretend.call()]
    assert log_obj.calls == [pretend.call()]
    assert config.registry["sentry"] is sentry_sdk
    assert config.add_request_method.calls == [
        pretend.call(sentry._sentry, name="sentry", reify=True)
    ]
    assert config.add_wsgi_middleware.calls == [pretend.call(SentryWsgiMiddleware)]
