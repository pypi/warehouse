# SPDX-License-Identifier: Apache-2.0

from warehouse.organizations.models import OrganizationApplicationStatus

NAME_SIMILARITY_THRESHOLD = 0.6
"""Lowest `difflib` ratio that still reads as the same organization."""

MIN_SUBSTRING_LENGTH = 3
"""Length both names must reach before one containing the other counts as a match.

Below it, `ar` would match `litestar`.
"""

OPEN_APPLICATION_STATUSES = {
    OrganizationApplicationStatus.Submitted,
    OrganizationApplicationStatus.Deferred,
    OrganizationApplicationStatus.MoreInformationNeeded,
}
"""Which status is considered open for an org app."""
