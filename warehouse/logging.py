# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging.config
import uuid

import structlog
import structlog.stdlib


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
            }
            record.msg = RENDERER(None, None, event_dict)

        return super().format(record)


def _create_id(request):
    return str(uuid.uuid4())


def _create_logger(request):
    logger = structlog.get_logger("warehouse.request")

    # This has to use **{} instead of just a kwarg because request.id is not
    # an allowed kwarg name.
    logger = logger.bind(**{"request.id": request.id})

    return logger


def includeme(config):
    # Configure the standard library logging
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structlog": {
                "()": "warehouse.logging.StructlogFormatter",
            },
        },
        "handlers": {
            "primary": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "structlog",
            },
            "sentry": {
                "class": "raven.handlers.logging.SentryHandler",
                "level": "ERROR",
                "dsn": config.registry.settings.get("sentry.dsn"),
                "transport": config.registry.settings.get("sentry.transport")
            },
        },
        "root": {
            "level": config.registry.settings.get("logging.level", "INFO"),
            "handlers": ["primary", "sentry"],
        },
    })

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
    )

    # Give every request a unique identifier
    config.add_request_method(_create_id, name="id", reify=True)

    # Add a log method to every request.
    config.add_request_method(_create_logger, name="log", reify=True)
