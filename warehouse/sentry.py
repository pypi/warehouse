# SPDX-License-Identifier: Apache-2.0

import sentry_sdk

from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.pyramid import PyramidIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.wsgi import SentryWsgiMiddleware
from webob.request import DisconnectionError


def _sentry(request):
    return request.registry["sentry"]


ignore_exceptions = (
    # For some reason we get periodic SystemExit exceptions, I think it is
    # because of OpenSSL generating a SIGABRT when OpenSSL_Die() is called, and
    # then Gunicorn treating that as being told to exit the process. Either way,
    # there isn't anything we can do about them, so they just cause noise.
    SystemExit,
    # Gunicorn internally raises these errors, and will catch them and handle
    # them correctly... however they have to first pass through our WSGI
    # middleware which is catching them and logging them. Instead we
    # will ignore them. We have to list these as strings, and list all
    # of them because we don't want to import Gunicorn in our application
    "gunicorn.http.errors.ParseException",
    "gunicorn.http.errors.NoMoreData",
    "gunicorn.http.errors.InvalidRequestLine",
    "gunicorn.http.errors.InvalidRequestMethod",
    "gunicorn.http.errors.InvalidHTTPVersion",
    "gunicorn.http.errors.InvalidHeader",
    "gunicorn.http.errors.InvalidHeaderName",
    "gunicorn.http.errors.InvalidChunkSize",
    "gunicorn.http.errors.ChunkMissingTerminator",
    "gunicorn.http.errors.LimitRequestLine",
    "gunicorn.http.errors.LimitRequestHeaders",
    "gunicorn.http.errors.InvalidProxyLine",
    "gunicorn.http.errors.ForbiddenProxyRequest",
    "gunicorn.http.errors.InvalidSchemeHeaders",
    # Webob raises this when the client disconnects, which we can't do anything about
    DisconnectionError,
)

ignore_strings = [
    "was sent code 131!",
    "was sent SIGINT!",
]


def before_send(event, hint):
    if "message" in event and any(s in event["message"] for s in ignore_strings):
        return None

    if "exc_info" in hint:
        exc_type, exc_value, tb = hint["exc_info"]
        if (
            exc_type in ignore_exceptions
            or type(exc_value).__name__ in ignore_exceptions
        ):
            return None
        else:
            return event
    return event


def includeme(config):
    # Initialize sentry and stash it in the registry
    sentry_sdk.init(
        dsn=config.registry.settings.get("sentry.dsn"),
        release=config.registry.settings.get("warehouse.commit"),
        transport=config.registry.settings.get("sentry.transport"),
        before_send=before_send,
        attach_stacktrace=True,
        integrations=[
            # This allows us to not create a tween
            # and a tween handler as it automatically
            # integrates with pyramid
            PyramidIntegration(),
            CeleryIntegration(),
            SqlalchemyIntegration(),
            LoggingIntegration(),
        ],
    )
    config.registry["sentry"] = sentry_sdk

    # Create a request method that'll get us the Sentry SDK in each request.
    config.add_request_method(_sentry, name="sentry", reify=True)

    # Wrap the WSGI object with the middle to catch any exceptions we don't
    # catch elsewhere.
    config.add_wsgi_middleware(SentryWsgiMiddleware)
