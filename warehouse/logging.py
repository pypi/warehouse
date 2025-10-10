# SPDX-License-Identifier: Apache-2.0

import logging.config
import os
import re
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


def _parse_gunicorn_access_log(logger, method_name, event_dict):
    """Parse Gunicorn logs into structlog ((only access logs)."""
    if event_dict.get("logger") != "gunicorn.access":
        return event_dict

    message = event_dict.get("event", "")

    # based on
    # https://albersdevelopment.net/2019/08/15/using-structlog-with-gunicorn/
    # and friends
    # Combined log format: host - user [time] "request" status size "referer" "user-agent"
    pattern = re.compile(
        r"(?P<remote_addr>\S+) \S+ (?P<user>\S+) "
        r'\[(?P<timestamp>.+?)\] "(?P<request>.+?)" '
        r"(?P<status>\d+) (?P<size>\S+) "
        r'"(?P<referrer>.*?)" "(?P<user_agent>.*?)"'
    )

    match = pattern.match(message)
    if not match:
        return event_dict

    fields = match.groupdict()

    # sanitize
    fields["user"] = None if fields["user"] == "-" else fields["user"]
    fields["status"] = int(fields["status"])
    fields["size"] = 0 if fields["size"] == "-" else int(fields["size"])
    fields["referrer"] = None if fields["referrer"] == "-" else fields["referrer"]

    # Parse "GET /path HTTP/1.1" into separate fields
    request_parts = fields["request"].split(" ", 2)
    if len(request_parts) >= 2:
        fields["method"] = request_parts[0]
        fields["path"] = request_parts[1]
        if len(request_parts) == 3:
            fields["protocol"] = request_parts[2]

    event_dict.update(fields)
    event_dict["event"] = "http_request"
    return event_dict


def _create_logger(request):
    # This has to use **{} instead of just a kwarg because request.id is not
    # an allowed kwarg name.
    return request_logger.bind(**{"request.id": request.id})


def includeme(config):
    # non structlog thigns
    foreign_pre_chain = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_datadog_context,
        _parse_gunicorn_access_log,
    ]

    # Configure the standard library logging
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structlog_formatter": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": RENDERER,
                    "foreign_pre_chain": foreign_pre_chain,
                }
            },
            "handlers": {
                "primary": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "structlog_formatter",
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
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Give every request a unique identifier
    config.add_request_method(_create_id, name="id", reify=True)

    # Add a log method to every request.
    config.add_request_method(_create_logger, name="log", reify=True)
