# SPDX-License-Identifier: Apache-2.0
"""
RFC 6750 Bearer error responses, with RFC 9457 problem details bodies.

See: https://www.rfc-editor.org/rfc/rfc6750#section-3
"""

from __future__ import annotations

from pyramid.httpexceptions import HTTPUnauthorized

from warehouse.api.problems import problem


def _quotable(value: str) -> str:
    """``value`` without the characters RFC 6750 section 3 excludes: anything
    outside printable ASCII, and ``"`` and ``\\``."""
    return "".join(c for c in value if " " <= c <= "~" and c not in '"\\')


def challenge(**params: str) -> str:
    """An RFC 6750 ``WWW-Authenticate`` value for the Bearer scheme."""
    attributes = ", ".join(
        f'{name}="{_quotable(value)}"' for name, value in params.items()
    )
    return f"Bearer {attributes}".strip()


def invalid_token(detail: str) -> HTTPUnauthorized:
    """A 401 ``invalid_token`` response that says why."""
    return problem(
        HTTPUnauthorized,
        detail,
        headers={
            "WWW-Authenticate": challenge(
                error="invalid_token", error_description=detail
            )
        },
    )
