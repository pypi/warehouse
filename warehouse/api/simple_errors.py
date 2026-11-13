# SPDX-License-Identifier: Apache-2.0

import logging

from pyramid.httpexceptions import HTTPError, HTTPInternalServerError, status_map
from pyramid.response import Response

from warehouse.api.problems import PROBLEM_CONTENT_TYPE, problem_details
from warehouse.utils.cors import _CORS_HEADERS

logger = logging.getLogger(__name__)


def is_simple_path(path):
    return path == "/simple" or path.startswith("/simple/")


def prepare_simple_error(response, detail=None):
    """Apply the error headers and return the replacement body, if one is needed."""
    headers = response.headers
    headers["Cache-Control"] = "no-store"
    headers.update(_CORS_HEADERS)
    for name in ("Surrogate-Control", "Expires"):
        if name in headers:
            del headers[name]

    if (response.content_type or "").lower() == PROBLEM_CONTENT_TYPE:
        return None

    # These describe the discarded body. Keep protocol headers such as Allow,
    # WWW-Authenticate and the Content-Range on a 416.
    for name in (
        "Content-Encoding",
        "Content-Language",
        "Content-Location",
        "Content-Disposition",
        "Content-MD5",
        "Content-Digest",
        "Repr-Digest",
        "Digest",
        "ETag",
        "Last-Modified",
        "Accept-Ranges",
    ):
        if name in headers:
            del headers[name]
    if exc := status_map.get(response.status_code):
        response.json = problem_details(exc, detail or exc.explanation)
    else:
        response.json = {"status": response.status_code}
    response.content_type = PROBLEM_CONTENT_TYPE
    return response.body


class SimpleAPIErrors:
    """Apply PEP 847 to the final WSGI status, including WebOb's range errors."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # PATH_INFO excludes the mount point and may contain undecodable bytes.
        if is_simple_path(environ.get("PATH_INFO", "")):
            return self._respond(environ, start_response)
        return self.app(environ, start_response)

    def _respond(self, environ, start_response):
        # Delay forwarding headers until the first output. This lets an exception
        # replace the response while the app is still preparing its body.
        pending_headers = None
        write = None
        replacement = None

        def send_headers():
            nonlocal write
            if write is None:
                write = start_response(*pending_headers)

        def write_body(data):
            if replacement is None:
                send_headers()
                write(data)

        def capture(status, headers, exc_info=None):
            nonlocal pending_headers, replacement
            if write is not None:
                return start_response(status, headers, exc_info)
            replacement = None
            if status.startswith(("4", "5")):
                response = Response(status=status, headerlist=headers, app_iter=())
                replacement = prepare_simple_error(response)
                headers = response.headerlist
            pending_headers = (status, headers)
            return write_body

        try:
            app_iter = self.app(environ, capture)
            try:
                if replacement is None:
                    for chunk in app_iter:
                        # An iterable can call start_response on its first iteration.
                        if replacement is not None:
                            break
                        if pending_headers is not None:
                            send_headers()
                        yield chunk
            finally:
                if hasattr(app_iter, "close"):
                    app_iter.close()
        except Exception as exc:
            if write is not None:
                raise
            if isinstance(exc, HTTPError):
                response = exc
            else:
                logger.exception("Unhandled Simple API error")
                response = HTTPInternalServerError()
            prepare_simple_error(response, response.detail)
            yield from response(environ, start_response)
            return

        send_headers()
        if replacement is not None and environ["REQUEST_METHOD"] != "HEAD":
            yield replacement
