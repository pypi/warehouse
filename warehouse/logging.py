# SPDX-License-Identifier: Apache-2.0

import logging.config
import os
import re
import threading
import uuid

import structlog

request_logger = structlog.get_logger("warehouse.request")

# Determine if we're in development mode
DEV_MODE = os.environ.get("WAREHOUSE_ENV") == "development"

# Choose renderer based on environment
RENDERER: structlog.dev.ConsoleRenderer | structlog.processors.JSONRenderer
if DEV_MODE:
    RENDERER = structlog.dev.ConsoleRenderer(colors=True)
else:
    RENDERER = structlog.processors.JSONRenderer()


class StructlogFormatter(logging.Formatter):
    # Pattern to parse Gunicorn access logs
    ACCESS_LOG_PATTERN = re.compile(
        r"(?P<remote_addr>[\d\.]+) - - "
        r"\[(?P<timestamp>[^\]]+)\] "
        r'"(?P<method>\w+) (?P<path>[^\s]+) (?P<protocol>[^"]+)" '
        r"(?P<status>\d+) (?P<size>\d+) "
        r'"(?P<referrer>[^"]*)" '
        r'"(?P<user_agent>[^"]*)"'
    )

    def format(self, record):
        # Handle Gunicorn access logs with structured parsing
        if record.name == "gunicorn.access":
            match = self.ACCESS_LOG_PATTERN.match(record.msg)
            if match:
                event_dict = {
                    "logger": record.name,
                    "level": record.levelname,
                    "event": "http_request",
                    "remote_addr": match.group("remote_addr"),
                    "method": match.group("method"),
                    "path": match.group("path"),
                    "protocol": match.group("protocol"),
                    "status": int(match.group("status")),
                    "response_size": int(match.group("size")),
                    "referrer": (
                        match.group("referrer")
                        if match.group("referrer") != "-"
                        else None
                    ),
                    "user_agent": match.group("user_agent"),
                    "thread": threading.get_ident(),
                }
                record.msg = RENDERER(None, record.levelname, event_dict)
            else:
                # Fallback for access logs that don't match the expected format
                event_dict = {
                    "logger": record.name,
                    "level": record.levelname,
                    "event": "http_request_unparsed",
                    "raw_message": record.msg,
                    "thread": threading.get_ident(),
                }
                record.msg = RENDERER(None, record.levelname, event_dict)
        # Handle other non-warehouse logs
        elif not record.name.startswith("warehouse."):
            # TODO: Is there a better way to handle this? Maybe we can figure
            #       out a way to pass this through the structlog processors
            #       instead of manually duplicating the side effects here?
            event_dict = {
                "logger": record.name,
                "level": record.levelname,
                "event": record.msg,
                "thread": threading.get_ident(),
            }
            record.msg = RENDERER(None, record.levelname, event_dict)

        return super().format(record)


def _create_id(request):
    return str(uuid.uuid4())


def _add_datadog_context(logger, method_name, event_dict):
    """Add Datadog trace context if available"""
    try:
        import ddtrace

        span = ddtrace.tracer.current_span()
        if span:
            event_dict["dd.trace_id"] = str(span.trace_id)
            event_dict["dd.span_id"] = str(span.span_id)
            event_dict["dd.service"] = span.service
        # deployment metadata
        event_dict["dd.env"] = os.environ.get("DD_ENV", "development")
        event_dict["dd.version"] = os.environ.get("DD_VERSION", "unknown")
    except (ImportError, AttributeError):
        pass
    return event_dict


def configure_celery_logging(logfile: str | None = None, loglevel: int = logging.INFO):
    """Configure unified structlog logging for Celery that handles all log types."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _add_datadog_context,
    ]
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=RENDERER,
        foreign_pre_chain=processors,
    )

    handler = logging.FileHandler(logfile) if logfile else logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(loglevel)

    structlog.configure(
        processors=processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def _create_logger(request):
    # This has to use **{} instead of just a kwarg because request.id is not
    # an allowed kwarg name.
    return request_logger.bind(**{"request.id": request.id})


def includeme(config):
    # Configure the standard library logging
    logging.config.dictConfig(
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
                    "level": config.registry.settings.get("logging.level", "INFO"),
                },
                "gunicorn.access": {
                    "propagate": False,
                    "handlers": ["primary"],
                    "level": config.registry.settings.get("logging.level", "INFO"),
                },
                "gunicorn.server": {
                    "propagate": False,
                    "handlers": ["primary"],
                    "level": config.registry.settings.get("logging.level", "INFO"),
                },
            },
            "root": {
                "level": config.registry.settings.get("logging.level", "INFO"),
                "handlers": ["primary"],
            },
        }
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _add_datadog_context,
            RENDERER,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Give every request a unique identifier
    config.add_request_method(_create_id, name="id", reify=True)

    # Add a log method to every request.
    config.add_request_method(_create_logger, name="log", reify=True)
