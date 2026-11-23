# SPDX-License-Identifier: Apache-2.0

import logging
import re

from pyramid.httpexceptions import HTTPError, HTTPInternalServerError, status_map
from pyramid.response import Response

from warehouse.api.problems import PROBLEM_CONTENT_TYPE, problem
from warehouse.utils.cors import _CORS_HEADERS

logger = logging.getLogger(__name__)

SIMPLE_PATH = re.compile(r"^/simple(?:/|\Z)")

# Discard metadata for the original body, but keep protocol headers such as
# Allow, WWW-Authenticate and the Content-Range on a 416.
_BODY_HEADERS = {
    "content-type",
    "content-length",
    "content-encoding",
    "content-language",
    "content-location",
    "content-disposition",
    "content-md5",
    "content-digest",
    "repr-digest",
    "digest",
    "etag",
    "last-modified",
    "accept-ranges",
}


def simple_error(response: Response) -> Response:
    """Return the original response if it already has a problem body."""
    for name in ("Surrogate-Control", "Expires"):
        if name in response.headers:
            del response.headers[name]

    if (response.content_type or "").lower() != PROBLEM_CONTENT_TYPE:
        if exc := status_map.get(response.status_code):
            error = problem(exc, getattr(response, "detail", None) or exc.explanation)
        else:
            error = Response(
                json={"status": response.status_code}, content_type=PROBLEM_CONTENT_TYPE
            )
        error.status = response.status
        error.headerlist.extend(
            (k, v) for k, v in response.headerlist if k.lower() not in _BODY_HEADERS
        )
        response = error

    response.headers.update(_CORS_HEADERS)
    response.headers["Cache-Control"] = "no-store"
    return response


class SimpleAPIErrors:
    """Apply PEP 847 to the final WSGI status, including WebOb's range errors."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # PATH_INFO excludes the mount point and may contain undecodable bytes.
        if SIMPLE_PATH.match(environ.get("PATH_INFO", "")):
            return self._respond(environ, start_response)
        return self.app(environ, start_response)

    def _respond(self, environ, start_response):
        # Delay forwarding headers until the first output. This lets an exception
        # replace the response while the app is still preparing its body.
        pending_headers = None
        write = None
        replacement = None

        def send(data=None):
            nonlocal write
            if write is None and pending_headers is not None:
                write = start_response(*pending_headers)
            if data is not None:
                write(data)

        def capture(status, headers, exc_info=None):
            nonlocal pending_headers, replacement
            if write is not None:
                return start_response(status, headers, exc_info)
            replacement = None
            if status.startswith(("4", "5")):
                response = Response(status=status, headerlist=headers, app_iter=())
                error = simple_error(response)
                if error is not response:
                    replacement = error
                    return lambda data: None
                headers = response.headerlist
            pending_headers = (status, headers)
            return send

        try:
            app_iter = self.app(environ, capture)
            try:
                if replacement is None:
                    for chunk in app_iter:
                        # An iterable can call start_response on its first iteration.
                        if replacement is not None:
                            break
                        send()
                        yield chunk
            finally:
                if hasattr(app_iter, "close"):
                    app_iter.close()
        except Exception as exc:
            if write is not None:
                raise
            if not isinstance(exc, HTTPError):
                logger.exception("Unhandled Simple API error")
                exc = HTTPInternalServerError()
            replacement = simple_error(exc)

        if replacement is None:
            send()
        else:
            yield from replacement(environ, start_response)
