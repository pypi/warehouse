# SPDX-License-Identifier: Apache-2.0
"""RFC 9457 - Problem Details for HTTP APIs

This module provides support for RFC 9457 (Problem Details for HTTP APIs),
a standardized format for describing errors in HTTP APIs.

This implementation is for server-side response generation, allowing PyPI
to return standardized error responses that clients (like pip) can parse.

Reference: https://www.rfc-editor.org/rfc/rfc9457
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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

    Additional extension members can be provided via the extensions dict.
    """

    status: int
    title: str
    detail: str | None = None
    type: str = "about:blank"
    instance: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for JSON serialization."""
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

        # Add any extension members
        result.update(self.extensions)

        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
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
    exc: HTTPException, detail: str | None = None, **extensions: Any
) -> ProblemDetails:
    """Create a ProblemDetails object from a Pyramid HTTPException.

    Args:
        exc: The HTTPException to convert
        detail: Optional detailed explanation. If not provided, uses exc.detail
        **extensions: Additional extension members to include

    Returns:
        A ProblemDetails object with information from the exception
    """
    # Use provided detail or fall back to exception's detail or explanation
    problem_detail = detail
    if problem_detail is None:
        problem_detail = getattr(exc, "detail", None) or getattr(
            exc, "explanation", None
        )

    return ProblemDetails(
        status=exc.status_code,
        title=exc.title or exc.status,
        detail=problem_detail,
        extensions=extensions,
    )


def accepts_problem_json(request) -> bool:
    """Check if the request accepts application/problem+json responses.

    Args:
        request: The Pyramid request object

    Returns:
        True if the client accepts RFC 9457 problem details format
    """
    # Check if the client explicitly accepts problem+json
    acceptable = request.accept.acceptable_offers([RFC9457_CONTENT_TYPE])
    return len(acceptable) > 0