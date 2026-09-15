# SPDX-License-Identifier: Apache-2.0

import json
import logging
import logging.config
import sys
import uuid

from datetime import timedelta
from types import SimpleNamespace

import gunicorn.config
import pytest
import structlog

from pyramid.tweens import EXCVIEW

from warehouse import logging as wlogging
from warehouse.config import Environment


def _includeme(pyramid_config, mocker, env):
    """
    Run includeme with the global side effects captured, returning the
    mocks for dictConfig and structlog.configure.
    """
    dict_config = mocker.patch.object(logging.config, "dictConfig", autospec=True)
    configure = mocker.patch.object(structlog, "configure", autospec=True)
    pyramid_config.registry.settings["warehouse.env"] = env

    wlogging.includeme(pyramid_config)

    return dict_config, configure


def _formatter_from(dict_config):
    """Instantiate the ProcessorFormatter exactly as dictConfig would."""
    spec = dict(dict_config.call_args.args[0]["formatters"]["structlog"])
    formatter_class = spec.pop("()")
    return formatter_class(**spec)


class TestIncludeme:
    @pytest.mark.parametrize(
        ("settings", "expected_level"),
        [({"logging.level": "DEBUG"}, "DEBUG"), ({}, "INFO")],
    )
    def test_log_level_setting(self, pyramid_config, mocker, settings, expected_level):
        pyramid_config.registry.settings.update(settings)
        dict_config, _ = _includeme(pyramid_config, mocker, Environment.production)

        config = dict_config.call_args.args[0]
        assert config["root"] == {"level": expected_level, "handlers": ["primary"]}
        for logger_name in ("gunicorn", "gunicorn.access", "gunicorn.error"):
            assert config["loggers"][logger_name] == {
                "propagate": False,
                "handlers": ["primary"],
                "level": expected_level,
            }
        assert config["loggers"]["datadog.dogstatsd"] == {"level": "ERROR"}

    def test_structlog_configure_chain(self, pyramid_config, mocker):
        _, configure = _includeme(pyramid_config, mocker, Environment.production)

        processors = configure.call_args.kwargs["processors"]
        assert processors[0] is structlog.stdlib.filter_by_level
        assert structlog.contextvars.merge_contextvars in processors
        assert processors[-1] is (
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter
        )
        assert (
            configure.call_args.kwargs["wrapper_class"] is structlog.stdlib.BoundLogger
        )
        assert isinstance(
            configure.call_args.kwargs["logger_factory"],
            structlog.stdlib.LoggerFactory,
        )
        assert configure.call_args.kwargs["cache_logger_on_first_use"] is True

    def test_adds_request_methods_and_tween(self, pyramid_config, mocker):
        add_request_method = mocker.patch.object(
            pyramid_config, "add_request_method", autospec=True
        )
        add_tween = mocker.patch.object(pyramid_config, "add_tween", autospec=True)

        _includeme(pyramid_config, mocker, Environment.production)

        assert add_request_method.call_args_list == [
            mocker.call(wlogging._create_id, name="id", reify=True),
            mocker.call(wlogging._create_logger, name="log", reify=True),
        ]
        add_tween.assert_called_once_with(
            "warehouse.logging.request_context_tween_factory", over=EXCVIEW
        )


class TestFormatterBehavior:
    """Exercise the real ProcessorFormatter the way dictConfig builds it."""

    @pytest.fixture
    def prod_formatter(self, pyramid_config, mocker):
        dict_config, _ = _includeme(pyramid_config, mocker, Environment.production)
        return _formatter_from(dict_config)

    @pytest.fixture
    def dev_formatter(self, pyramid_config, mocker):
        dict_config, _ = _includeme(pyramid_config, mocker, Environment.development)
        return _formatter_from(dict_config)

    def test_foreign_record_renders_json_with_extras(self, prod_formatter):
        record = logging.LogRecord(
            "gunicorn.access", logging.INFO, "", 0, "http_request", None, None
        )
        record.method = "GET"
        record.status = 404

        output = json.loads(prod_formatter.format(record))

        assert output["logger"] == "gunicorn.access"
        assert output["level"] == "info"
        assert output["event"] == "http_request"
        assert output["method"] == "GET"
        assert output["status"] == 404
        assert "timestamp" in output

    def test_foreign_record_positional_args_interpolated(self, prod_formatter):
        record = logging.LogRecord(
            "another.logger", logging.INFO, "", 0, "Purging %s", ("a-key",), None
        )

        output = json.loads(prod_formatter.format(record))

        assert output["event"] == "Purging a-key"

    def test_foreign_record_renders_console_in_dev(self, dev_formatter):
        record = logging.LogRecord(
            "gunicorn.access", logging.INFO, "", 0, "http_request", None, None
        )
        record.method = "GET"

        output = dev_formatter.format(record)

        assert not output.startswith("{")
        assert "http_request" in output
        assert "method" in output
        assert "GET" in output

    def test_foreign_record_formats_exceptions(self, prod_formatter):
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                "another.logger",
                logging.ERROR,
                "",
                0,
                "task failed",
                None,
                exc_info=sys.exc_info(),
            )

        output = json.loads(prod_formatter.format(record))

        assert output["event"] == "task failed"
        assert "ValueError: boom" in output["exception"]


class TestRequestContextTween:
    def test_binds_request_id_during_request(self, pyramid_request, mocker):
        pyramid_request.id = "a-request-id"
        seen_context = {}
        response = mocker.sentinel.response

        def handler(request):
            seen_context.update(structlog.contextvars.get_contextvars())
            return response

        tween = wlogging.request_context_tween_factory(
            handler, pyramid_request.registry
        )

        assert tween(pyramid_request) is response
        assert seen_context["request.id"] == "a-request-id"

    def test_stashes_request_id_for_access_log(self, pyramid_request):
        """The environ outlives the request, where gunicorn's access hook
        picks the id up after the tween chain has unwound."""
        pyramid_request.id = "a-request-id"
        tween = wlogging.request_context_tween_factory(
            lambda request: None, pyramid_request.registry
        )

        tween(pyramid_request)

        assert pyramid_request.environ["warehouse.request_id"] == "a-request-id"

    def test_clears_binding_after_request(self, pyramid_request):
        pyramid_request.id = "a-request-id"
        tween = wlogging.request_context_tween_factory(
            lambda request: None, pyramid_request.registry
        )

        tween(pyramid_request)

        assert "request.id" not in structlog.contextvars.get_contextvars()


class TestGunicornLogger:
    @pytest.fixture
    def access_records(self):
        """Capture records on the global gunicorn.access logger, restoring after."""
        access_log = logging.getLogger("gunicorn.access")
        previous_handlers = access_log.handlers[:]
        access_log.handlers = []
        records = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        access_log.addHandler(_Capture())
        try:
            yield records
        finally:
            access_log.handlers = previous_handlers

    @pytest.fixture
    def gunicorn_cfg(self):
        cfg = gunicorn.config.Config()
        cfg.set("accesslog", "-")
        return cfg

    def _environ(self):
        return {
            "REMOTE_ADDR_HASHED": "d1c8c5c2cf5a",
            "REMOTE_ADDR": "127.0.0.1",
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/simple/example/",
            "QUERY_STRING": "",
            "RAW_URI": "/simple/example%2E/",
            "SERVER_PROTOCOL": "HTTP/1.1",
            "HTTP_REFERER": "https://example.com/",
            "HTTP_USER_AGENT": "PyCharm/2026.2",
            "GEOIP_COUNTRY_CODE": "US",
            "warehouse.request_id": "a-request-id",
        }

    def test_access_emits_structured_fields(self, gunicorn_cfg, access_records):
        logger = wlogging.GunicornLogger(gunicorn_cfg)
        resp = SimpleNamespace(status="404 Not Found", sent=13, headers=[])

        logger.access(
            resp, None, self._environ(), timedelta(seconds=1, milliseconds=234)
        )

        (record,) = access_records
        assert record.msg == "http_request"
        assert record.remote_addr == "d1c8c5c2cf5a"
        assert record.method == "GET"
        assert record.path == "/simple/example/"
        assert record.query == ""
        assert record.raw_uri == "/simple/example%2E/"
        assert record.protocol == "HTTP/1.1"
        assert record.status == 404
        assert record.size == 13
        assert record.referrer == "https://example.com/"
        assert record.user_agent == "PyCharm/2026.2"
        assert record.country == "US"
        assert record.duration_ms == pytest.approx(1234.0)
        assert record.__dict__["request.id"] == "a-request-id"

    def test_access_integer_status(self, gunicorn_cfg, access_records):
        logger = wlogging.GunicornLogger(gunicorn_cfg)
        resp = SimpleNamespace(status=200, sent=0, headers=[])

        logger.access(resp, None, self._environ(), timedelta(milliseconds=5))

        (record,) = access_records
        assert record.status == 200

    def test_access_falls_back_to_remote_addr(self, gunicorn_cfg, access_records):
        logger = wlogging.GunicornLogger(gunicorn_cfg)
        resp = SimpleNamespace(status="200 OK", sent=0, headers=[])
        environ = self._environ()
        del environ["REMOTE_ADDR_HASHED"]

        logger.access(resp, None, environ, timedelta(milliseconds=5))

        (record,) = access_records
        assert record.remote_addr == "127.0.0.1"

    def test_access_disabled_does_not_log(self, access_records):
        logger = wlogging.GunicornLogger(gunicorn.config.Config())
        resp = SimpleNamespace(status="200 OK", sent=0, headers=[])

        logger.access(resp, None, self._environ(), timedelta(milliseconds=5))

        assert access_records == []


def test_create_id(mocker):
    mocker.patch.object(uuid, "uuid4", autospec=True, return_value="a fake uuid")

    request = mocker.sentinel.request

    assert wlogging._create_id(request) == "a fake uuid"


def test_create_logging(pyramid_request):
    """request.log is the shared logger; request.id arrives via contextvars."""
    assert wlogging._create_logger(pyramid_request) is wlogging.request_logger
