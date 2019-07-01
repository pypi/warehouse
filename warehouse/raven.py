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

import raven
import raven.middleware

from pyramid.tweens import EXCVIEW, INGRESS
from raven.utils.serializer.base import Serializer
from raven.utils.serializer.manager import manager as serialization_manager

from warehouse.sessions import InvalidSession


class InvalidSessionSerializer(Serializer):

    types = (InvalidSession,)

    def serialize(self, value, **kwargs):
        return "<InvalidSession>"


# We need to register our SessionSerializer before any of the other serializers
# in the list.
serializer_registry = serialization_manager._SerializationManager__registry
serializer_registry.insert(0, InvalidSessionSerializer)


def raven_tween_factory(handler, registry):
    def raven_tween(request):
        try:
            return handler(request)
        except:  # noqa
            request.raven.captureException()
            raise

    return raven_tween


def _raven(request):
    request.add_finished_callback(lambda r: r.raven.context.clear())
    return request.registry["raven.client"]


def includeme(config):
    # Create a client and stash it in the registry
    client = raven.Client(
        dsn=config.registry.settings.get("sentry.dsn"),
        include_paths=["warehouse"],
        release=config.registry.settings["warehouse.commit"],
        transport=config.registry.settings.get("sentry.transport"),
        # For some reason we get periodic SystemExit exceptions, I think it is because
        # of OpenSSL generating a SIGABRT when OpenSSL_Die() is called, and then
        # Gunicorn treating that as being told to exit the process. Either way, there
        # isn't anything we can do about them, so they just cause noise.
        ignore_exceptions=[
            # For some reason we get periodic SystemExit exceptions, I think it is
            # because of OpenSSL generating a SIGABRT when OpenSSL_Die() is called, and
            # then Gunicorn treating that as being told to exit the process. Either way,
            # there isn't anything we can do about them, so they just cause noise.
            SystemExit,
            # Gunicorn internally raises these errors, and will catch them and handle
            # them correctly... however they have to first pass through our WSGI
            # middleware for Raven which is catching them and logging them. Instead we
            # will ignore them.
            # We have to list these as strings, and list all of them because we don't
            # want to import Gunicorn in our application, and when using strings Raven
            # doesn't handle inheritance.
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
        ],
    )
    config.registry["raven.client"] = client

    # Create a request method that'll get us the Raven client in each request.
    config.add_request_method(_raven, name="raven", reify=True)

    # Add a tween that will handle catching any exceptions that get raised.
    config.add_tween(
        "warehouse.raven.raven_tween_factory",
        under=["pyramid_debugtoolbar.toolbar_tween_factory", INGRESS],
        over=EXCVIEW,
    )

    # Wrap the WSGI object with the middle to catch any exceptions we don't
    # catch elsewhere.
    config.add_wsgi_middleware(raven.middleware.Sentry, client=client)
