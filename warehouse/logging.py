# SPDX-License-Identifier: Apache-2.0

import logging.config
import threading
import uuid

import structlog

request_logger = structlog.get_logger("warehouse.request")

RENDERER = structlog.processors.JSONRenderer()


class StructlogFormatter(logging.Formatter):
    def format(self, record):
        # TODO: Figure out a better way of handling this besides just looking
        #       at the logger name, ideally this would have some way to
        #       really differentiate between log items which were logged by
        #       structlog and which were not.
        if not record.name.startswith("warehouse."):
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
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
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
