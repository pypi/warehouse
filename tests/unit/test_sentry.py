# SPDX-License-Identifier: Apache-2.0

import pytest
import sentry_sdk

from warehouse import sentry


def test_sentry_request_method(pyramid_request, mocker):
    sentry_obj = mocker.sentinel.sentry_sdk
    pyramid_request.registry["sentry"] = sentry_obj

    assert sentry._sentry(pyramid_request) is sentry_obj


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


def test_includeme(pyramid_config, mocker):
    init_obj = mocker.patch.object(sentry_sdk, "init", return_value="1")
    pyramid_obj = mocker.patch("warehouse.sentry.PyramidIntegration", return_value="2")
    celery_obj = mocker.patch("warehouse.sentry.CeleryIntegration", return_value="3")
    sql_obj = mocker.patch("warehouse.sentry.SqlalchemyIntegration", return_value="4")
    log_obj = mocker.patch("warehouse.sentry.LoggingIntegration", return_value="5")
    add_request_method = mocker.patch.object(
        pyramid_config, "add_request_method", autospec=True
    )

    pyramid_config.registry.settings.update(
        {
            "warehouse.commit": "rand3rfgkn3424",
            "sentry.dsn": "test_dsn",
            "sentry.transport": "proxy_transport",
        }
    )

    sentry.includeme(pyramid_config)

    init_obj.assert_called_once_with(
        dsn="test_dsn",
        release="rand3rfgkn3424",
        transport="proxy_transport",
        before_send=sentry.before_send,
        attach_stacktrace=True,
        integrations=["2", "3", "4", "5"],
    )
    pyramid_obj.assert_called_once_with()
    celery_obj.assert_called_once_with()
    sql_obj.assert_called_once_with()
    log_obj.assert_called_once_with()
    assert pyramid_config.registry["sentry"] is sentry_sdk
    add_request_method.assert_called_once_with(
        sentry._sentry, name="sentry", reify=True
    )
