# SPDX-License-Identifier: Apache-2.0
"""RFC 9457 - Problem Details for HTTP APIs.

This module provides support for RFC 9457 (Problem Details for HTTP APIs),
a standardized format for describing errors in HTTP APIs.

This implementation is for server-side response generation, allowing PyPI
to return standardized error responses that clients can parse.

Reference: https://www.rfc-editor.org/rfc/rfc9457.html
"""

from __future__ import annotations

import json

from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

from pyramid.httpexceptions import HTTPException

RFC9457_CONTENT_TYPE = "application/problem+json"


@dataclass
class ProblemDetails:
    """Represents an RFC 9457 Problem Details object.

    This class encapsulates the core fields defined in RFC 9457:
    - status: The HTTP status code
    - title: A short, human-readable summary of the problem type
    - detail: A human-readable explanation specific to this occurrence
    - type: A URI reference that identifies the problem type
    - instance: A URI reference that identifies the specific occurrence

    Additional extension members can be provided via the extensions dict.
    """

    status: int
    title: str
    detail: str | None = None
    type: str = "about:blank"
    instance: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict, kw_only=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for JSON serialization.

        Returns a dictionary representation following RFC 9457 structure.
        The 'type' field is omitted when it equals 'about:blank' (default).
        """
        result: dict[str, Any] = {
            "status": self.status,
            "title": self.title,
        }

        if self.type != "about:blank":
            result["type"] = self.type

        if self.detail:
            result["detail"] = self.detail

        if self.instance:
            result["instance"] = self.instance

        forbidden_keys = {"status", "title", "detail", "type", "instance"}
        if any(key in self.extensions for key in forbidden_keys):
            raise ValueError(
                f"Extensions cannot override required RFC 9457 fields: "
                f"{forbidden_keys}"
            )

        result.update(self.extensions)

        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self) -> str:
        """Human-readable string representation for logging."""
        parts = []

        if self.title:
            parts.append(f"{self.title}")
        if self.status:
            parts.append(f"(Status: {self.status})")
        if self.detail:
            parts.append(f"\n{self.detail}")

        return " ".join(parts) if parts else "Unknown problem"


def problem_details_from_exception(
    exc: HTTPException,
    detail: str | None = None,
    type: str = "about:blank",
    **extensions: Any,
) -> ProblemDetails:
    if detail is None:
        problem_detail = getattr(exc, "detail", None) or getattr(
            exc, "explanation", None
        )
    else:
        problem_detail = detail

    title = exc.title or exc.status

    # RFC 9457: When "about:blank" is used, the title SHOULD be the same
    # as the recommended HTTP status phrase for that code
    if type == "about:blank":
        try:
            title = HTTPStatus(exc.status_code).phrase
        except ValueError:
            pass

    return ProblemDetails(
        status=exc.status_code,
        title=title,
        detail=problem_detail,
        type=type,
        extensions=extensions,
    )
