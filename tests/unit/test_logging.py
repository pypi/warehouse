# SPDX-License-Identifier: Apache-2.0

import json
import logging
import logging.config
import threading
import uuid

from unittest import mock

import pretend
import pytest
import structlog

from warehouse import logging as wlogging


class TestStructlogFormatter:
    def test_warehouse_logger_no_renderer(self):
        formatter = wlogging.StructlogFormatter()
        record = logging.LogRecord(
            "warehouse.request", logging.INFO, None, None, "the message", None, None
        )

        assert formatter.format(record) == "the message"

    def test_non_warehouse_logger_renders(self):
        formatter = wlogging.StructlogFormatter()
        record = logging.LogRecord(
            "another.logger", logging.INFO, None, None, "the message", None, None
        )

        assert json.loads(formatter.format(record)) == {
            "logger": "another.logger",
            "level": "INFO",
            "event": "the message",
            "thread": threading.get_ident(),
        }

    def test_gunicorn_access_log_parsing(self):
        formatter = wlogging.StructlogFormatter()
        access_log_line = (
            "bce7b3d78e73edf3cb8949bec7c52eba9727c4083417be33eca8afc5f31ef355 - - "
            '[11/Aug/2025:21:01:13 +0000] "GET /pypi/b5ee/json HTTP/1.1" 404 24 '
            '"-" "dependabot-core/0.325.1 excon/1.2.5 ruby/3.4.5 (x86_64-linux) '
            '(+https://github.com/dependabot/dependabot-core)"'
        )
        record = logging.LogRecord(
            "gunicorn.access", logging.INFO, None, None, access_log_line, None, None
        )

        result = json.loads(formatter.format(record))

        assert result["logger"] == "gunicorn.access"
        assert result["level"] == "INFO"
        assert result["event"] == "http_request"
        expected_id = "bce7b3d78e73edf3cb8949bec7c52eba9727c4083417be33eca8afc5f31ef355"
        assert result["request_id"] == expected_id
        assert result["method"] == "GET"
        assert result["path"] == "/pypi/b5ee/json"
        assert result["protocol"] == "HTTP/1.1"
        assert result["status"] == 404
        assert result["response_size"] == 24
        assert result["referrer"] is None
        assert "dependabot-core" in result["user_agent"]
        assert "thread" in result

    def test_gunicorn_access_log_parsing_with_referrer(self):
        formatter = wlogging.StructlogFormatter()
        access_log_line = (
            "test-id-123 - - "
            '[12/Aug/2025:10:30:45 +0000] "POST /simple/upload HTTP/1.1" 200 500 '
            '"https://pypi.org/project/test/" "Mozilla/5.0 (compatible; test)"'
        )
        record = logging.LogRecord(
            "gunicorn.access", logging.INFO, None, None, access_log_line, None, None
        )

        result = json.loads(formatter.format(record))

        assert result["request_id"] == "test-id-123"
        assert result["method"] == "POST"
        assert result["path"] == "/simple/upload"
        assert result["status"] == 200
        assert result["response_size"] == 500
        assert result["referrer"] == "https://pypi.org/project/test/"
        assert result["user_agent"] == "Mozilla/5.0 (compatible; test)"

    def test_gunicorn_access_log_unparsable(self):
        formatter = wlogging.StructlogFormatter()
        malformed_log = "this is not a valid access log format"
        record = logging.LogRecord(
            "gunicorn.access", logging.INFO, None, None, malformed_log, None, None
        )

        result = json.loads(formatter.format(record))

        assert result["logger"] == "gunicorn.access"
        assert result["level"] == "INFO"
        assert result["event"] == "http_request_unparsed"
        assert result["raw_message"] == "this is not a valid access log format"
        assert "thread" in result


def test_create_id(monkeypatch):
    uuid4 = pretend.call_recorder(lambda: "a fake uuid")
    monkeypatch.setattr(uuid, "uuid4", uuid4)

    request = pretend.stub()

    assert wlogging._create_id(request) == "a fake uuid"


def test_create_logging(monkeypatch):
    bound_logger = pretend.stub()
    logger = pretend.stub(bind=pretend.call_recorder(lambda **kw: bound_logger))
    monkeypatch.setattr(wlogging, "request_logger", logger)

    request = pretend.stub(id="request id")

    assert wlogging._create_logger(request) is bound_logger
    assert logger.bind.calls == [pretend.call(**{"request.id": "request id"})]


@pytest.mark.parametrize(
    ("settings", "expected_level"),
    [({"logging.level": "DEBUG"}, "DEBUG"), ({}, "INFO")],
)
def test_includeme(monkeypatch, settings, expected_level):
    dict_config = pretend.call_recorder(lambda c: None)
    monkeypatch.setattr(logging.config, "dictConfig", dict_config)

    configure = pretend.call_recorder(lambda **kw: None)
    monkeypatch.setattr(structlog, "configure", configure)

    config = pretend.stub(
        registry=pretend.stub(settings=settings),
        add_request_method=pretend.call_recorder(lambda fn, name, reify: None),
    )

    wlogging.includeme(config)

    assert dict_config.calls == [
        pretend.call(
            {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "structlog": {"()": "warehouse.logging.StructlogFormatter"}
                },
                "handlers": {
                    "primary": {
                        "class": "logging.StreamHandler",
                        "stream": "ext://sys.stdout",
                        "formatter": "structlog",
                    },
                },
                "loggers": {
                    "datadog.dogstatsd": {"level": "ERROR"},
                    "gunicorn": {
                        "propagate": False,
                        "handlers": ["primary"],
                        "level": expected_level,
                    },
                    "gunicorn.access": {
                        "propagate": False,
                        "handlers": ["primary"],
                        "level": expected_level,
                    },
                    "gunicorn.server": {
                        "propagate": False,
                        "handlers": ["primary"],
                        "level": expected_level,
                    },
                },
                "root": {"level": expected_level, "handlers": ["primary"]},
            }
        )
    ]
    assert configure.calls == [
        pretend.call(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                mock.ANY,  # PositionalArgumentsFormatter
                mock.ANY,  # TimeStamper
                mock.ANY,  # StackInfoRenderer
                structlog.processors.format_exc_info,
                mock.ANY,  # _add_datadog_context
                wlogging.RENDERER,
            ],
            logger_factory=mock.ANY,
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    ]
    assert isinstance(
        configure.calls[0].kwargs["processors"][3],
        structlog.stdlib.PositionalArgumentsFormatter,
    )
    assert isinstance(
        configure.calls[0].kwargs["processors"][4],
        structlog.processors.TimeStamper,
    )
    assert isinstance(
        configure.calls[0].kwargs["processors"][5],
        structlog.processors.StackInfoRenderer,
    )
    assert isinstance(
        configure.calls[0].kwargs["logger_factory"], structlog.stdlib.LoggerFactory
    )
    assert config.add_request_method.calls == [
        pretend.call(wlogging._create_id, name="id", reify=True),
        pretend.call(wlogging._create_logger, name="log", reify=True),
    ]
