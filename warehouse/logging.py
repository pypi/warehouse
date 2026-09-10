# SPDX-License-Identifier: Apache-2.0

import logging.config
import typing
import uuid

import gunicorn.glogging
import structlog

from pyramid.tweens import EXCVIEW

from warehouse.config import Environment

if typing.TYPE_CHECKING:
    from pyramid.config import Configurator
    from pyramid.registry import Registry
    from pyramid.request import Request
    from pyramid.response import Response

request_logger = structlog.get_logger("warehouse.request")


class GunicornLogger(gunicorn.glogging.Logger):
    """
    A gunicorn logger that emits access logs as structured events instead of
    a pre-formatted Apache combined log line, so the shared ProcessorFormatter
    can render them as columns in development and JSON in production.
    """

    def access(self, resp, req, environ, request_time) -> None:
        if not self.access_log_enabled:
            return

        # Mirror gunicorn's own defensive handling from Logger.atoms(): resp
        # status is usually a string like "404 Not Found", but may be an int.
        status = resp.status
        if isinstance(status, str):
            status = int(status.split(None, 1)[0])

        self.access_log.info(
            "http_request",
            extra={
                # ProxyFixer has already resolved the hashed client IP into
                # REMOTE_ADDR_HASHED (and stripped the CDN headers) by the
                # time the access hook runs; never log the raw address unless
                # no hash is available (e.g. very early requests).
                "remote_addr": environ.get("REMOTE_ADDR_HASHED")
                or environ.get("REMOTE_ADDR"),
                "method": environ.get("REQUEST_METHOD"),
                "path": environ.get("PATH_INFO"),
                "query": environ.get("QUERY_STRING"),
                # PATH_INFO is percent-decoded; keep the exact wire bytes too,
                # since probes hide in the encoding (e.g. /simple/foo%2E%2E/).
                "raw_uri": environ.get("RAW_URI"),
                "protocol": environ.get("SERVER_PROTOCOL"),
                "status": status,
                "size": getattr(resp, "sent", None),
                "referrer": environ.get("HTTP_REFERER"),
                "user_agent": environ.get("HTTP_USER_AGENT"),
                # Resolved by ProxyFixer from the CDN's GeoIP headers.
                "country": environ.get("GEOIP_COUNTRY_CODE"),
                "duration_ms": request_time.total_seconds() * 1000,
                # Stashed by request_context_tween so access lines join the
                # app logs emitted during the same request.
                "request.id": environ.get("warehouse.request_id"),
            },
        )


def request_context_tween_factory(
    handler: typing.Callable[[Request], Response], registry: Registry
) -> typing.Callable[[Request], Response]:
    """
    Bind the request id into structlog's contextvars for the duration of the
    request, so module-level loggers used during request handling carry it too.
    """

    def request_context_tween(request: Request) -> Response:
        # The environ outlives the request: gunicorn's access hook reads the
        # stashed id after the tween chain (and its contextvars) unwound.
        request.environ["warehouse.request_id"] = request.id

        # This has to use **{} because request.id is not an allowed kwarg name.
        with structlog.contextvars.bound_contextvars(**{"request.id": request.id}):
            return handler(request)

    return request_context_tween


def _create_id(request):
    return str(uuid.uuid4())


def _create_logger(request):
    # request.id arrives via contextvars (bound by the tween below, or by
    # WarehouseTask.get_request in workers), so no per-request bind is needed.
    return request_logger


def includeme(config: Configurator) -> None:
    settings = config.registry.settings

    # Render logs as aligned, colored columns in development, and as JSON
    # everywhere else so the aggregator receives one parseable object per line.
    if settings.get("warehouse.env") == Environment.development:
        renderer: structlog.typing.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    level = settings.get("logging.level", "INFO")

    # Applied to every record, structlog-born and foreign alike, so both
    # populations end up with the same shape.
    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
    ]

    # Normalizes log records that did not originate from structlog (gunicorn,
    # celery, any library using logging.getLogger) into event dicts, before
    # the shared renderer sees them. ExtraAdder lifts `extra={...}` kwargs
    # into the event dict.
    foreign_pre_chain = [*shared_processors, structlog.stdlib.ExtraAdder()]

    # Configure the standard library logging: a single handler whose
    # ProcessorFormatter renders structlog-born and foreign records alike.
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structlog": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        renderer,
                    ],
                    "foreign_pre_chain": foreign_pre_chain,
                }
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
                    "level": level,
                },
                "gunicorn.access": {
                    "propagate": False,
                    "handlers": ["primary"],
                    "level": level,
                },
                "gunicorn.error": {
                    "propagate": False,
                    "handlers": ["primary"],
                    "level": level,
                },
            },
            "root": {"level": level, "handlers": ["primary"]},
        }
    )

    # Configure structlog: build event dicts and hand them to the
    # ProcessorFormatter above instead of rendering here.
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            *shared_processors,
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

    # Make the request id ambient context for all loggers during a request,
    # including exception views.
    config.add_tween("warehouse.logging.request_context_tween_factory", over=EXCVIEW)
