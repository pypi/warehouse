# SPDX-License-Identifier: Apache-2.0
"""
RFC 9457 problem details, the body of the danger API's error responses.

See: https://www.rfc-editor.org/rfc/rfc9457
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pyramid.httpexceptions import HTTPError

PROBLEM_CONTENT_TYPE: Final = "application/problem+json"


def problem[E: HTTPError](
    exc_class: type[E],
    detail: str,
    /,
    *,
    headers: Mapping[str, str] | None = None,
    **extensions: object,
) -> E:
    """
    An error response with a problem details body. ``type`` is
    ``about:blank``, so ``title`` is the HTTP status phrase and ``detail``
    says what went wrong. ``extensions`` become extension members; they
    can't replace the standard ones. An error describes one request, so it
    is never cached.

    See: https://www.rfc-editor.org/rfc/rfc9457#section-4.2.1
    """
    return exc_class(
        json={
            **extensions,
            "type": "about:blank",
            "title": exc_class.title,
            "status": exc_class.code,
            "detail": detail,
        },
        content_type=PROBLEM_CONTENT_TYPE,
        headers={**(headers or {}), "Cache-Control": "no-store"},
    )
