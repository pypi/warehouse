# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyramid.request import Request

# Valid time periods for filtering
ALLOWED_DAYS = (30, 60, 90)
DEFAULT_DAYS = 30


def parse_days_param(request: Request, allowed: tuple[int, ...] = ALLOWED_DAYS) -> int:
    """Parse and validate the 'days' query parameter."""
    try:
        days = int(request.params.get("days", DEFAULT_DAYS))
        return days if days in allowed else DEFAULT_DAYS
    except (ValueError, TypeError):
        return DEFAULT_DAYS
