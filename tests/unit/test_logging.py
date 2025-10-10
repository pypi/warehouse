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
    # timestamper #18843
    assert isinstance(
        configure.calls[0].kwargs["processors"][4],
        structlog.processors.TimeStamper,
    )
    assert isinstance(
        configure.calls[0].kwargs["processors"][5],
        structlog.processors.StackInfoRenderer,
    )
    # _add_datadog_context #18843
    assert configure.calls[0].kwargs["processors"][7] == wlogging._add_datadog_context
    assert isinstance(
        configure.calls[0].kwargs["logger_factory"], structlog.stdlib.LoggerFactory
    )
    assert config.add_request_method.calls == [
        pretend.call(wlogging._create_id, name="id", reify=True),
        pretend.call(wlogging._create_logger, name="log", reify=True),
    ]


def test_add_datadog_context(monkeypatch):
    monkeypatch.setenv("DD_ENV", "production")
    monkeypatch.setenv("DD_VERSION", "1.2.3")

    event_dict = {"event": "test"}
    result = wlogging._add_datadog_context(None, None, event_dict)

    assert result["dd.env"] == "production"
    assert result["dd.version"] == "1.2.3"


def test_add_datadog_context_with_span(monkeypatch):
    """Test Datadog context with an active span."""
    import sys

    mock_span = pretend.stub(trace_id=123, span_id=456, service="test-svc")
    mock_tracer = pretend.stub(current_span=lambda: mock_span)
    mock_ddtrace = pretend.stub(tracer=mock_tracer)

    sys.modules["ddtrace"] = mock_ddtrace
    monkeypatch.setenv("DD_ENV", "prod")
    monkeypatch.setenv("DD_VERSION", "2.0")

    try:
        event_dict = {"event": "test"}
        result = wlogging._add_datadog_context(None, None, event_dict)

        assert result["dd.trace_id"] == "123"
        assert result["dd.span_id"] == "456"
        assert result["dd.service"] == "test-svc"
    finally:
        del sys.modules["ddtrace"]


def test_configure_celery_logging(monkeypatch):
    configure = pretend.call_recorder(lambda **kw: None)
    monkeypatch.setattr(structlog, "configure", configure)

    mock_handler = pretend.stub(setFormatter=pretend.call_recorder(lambda f: None))
    mock_logger = pretend.stub(
        handlers=pretend.stub(clear=pretend.call_recorder(lambda: None)),
        setLevel=pretend.call_recorder(lambda level: None),
        addHandler=pretend.call_recorder(lambda add_handler: None),
        removeHandler=pretend.call_recorder(lambda remove_handler: None),
    )
    monkeypatch.setattr(logging, "getLogger", lambda: mock_logger)
    monkeypatch.setattr(logging, "StreamHandler", lambda: mock_handler)

    wlogging.configure_celery_logging()

    # Verify handlers cleared and new one added
    assert mock_logger.handlers.clear.calls == [pretend.call()]
    assert len(mock_logger.addHandler.calls) == 1
    assert mock_logger.setLevel.calls == [pretend.call(logging.INFO)]

    # Verify processors
    processors = configure.calls[0].kwargs["processors"]
    assert structlog.contextvars.merge_contextvars in processors
    assert wlogging._add_datadog_context in processors
