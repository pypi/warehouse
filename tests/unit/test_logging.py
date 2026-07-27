# SPDX-License-Identifier: Apache-2.0

import json
import logging
import logging.config
import threading
import uuid

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


def test_create_id(mocker):
    mocker.patch.object(uuid, "uuid4", autospec=True, return_value="a fake uuid")

    request = mocker.sentinel.request

    assert wlogging._create_id(request) == "a fake uuid"


def test_create_logging(pyramid_request, mocker):
    bound_logger = mocker.sentinel.bound_logger
    logger = mocker.patch.object(wlogging, "request_logger")
    logger.bind.return_value = bound_logger

    pyramid_request.id = "request id"

    assert wlogging._create_logger(pyramid_request) is bound_logger
    logger.bind.assert_called_once_with(**{"request.id": "request id"})


@pytest.mark.parametrize(
    ("settings", "expected_level"),
    [({"logging.level": "DEBUG"}, "DEBUG"), ({}, "INFO")],
)
def test_includeme(pyramid_config, mocker, settings, expected_level):
    dict_config = mocker.patch.object(logging.config, "dictConfig", autospec=True)
    configure = mocker.patch.object(structlog, "configure", autospec=True)
    add_request_method = mocker.patch.object(
        pyramid_config, "add_request_method", autospec=True
    )
    pyramid_config.registry.settings.update(settings)

    wlogging.includeme(pyramid_config)

    dict_config.assert_called_once_with(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"structlog": {"()": "warehouse.logging.StructlogFormatter"}},
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
    configure.assert_called_once_with(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            mocker.ANY,
            mocker.ANY,
            structlog.processors.format_exc_info,
            wlogging.RENDERER,
        ],
        logger_factory=mocker.ANY,
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    assert isinstance(
        configure.call_args.kwargs["processors"][3],
        structlog.stdlib.PositionalArgumentsFormatter,
    )
    assert isinstance(
        configure.call_args.kwargs["processors"][4],
        structlog.processors.StackInfoRenderer,
    )
    assert isinstance(
        configure.call_args.kwargs["logger_factory"], structlog.stdlib.LoggerFactory
    )
    assert add_request_method.call_args_list == [
        mocker.call(wlogging._create_id, name="id", reify=True),
        mocker.call(wlogging._create_logger, name="log", reify=True),
    ]
