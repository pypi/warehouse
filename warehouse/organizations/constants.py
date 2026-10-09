# SPDX-License-Identifier: Apache-2.0

"""Constants related to PyPI organizations."""

import datetime

from warehouse.organizations.models import OrganizationApplicationStatus

CLEANUP_AFTER = datetime.timedelta(days=30)
"""How long to keep declined organization applications before deletion."""

## -- Things rleating to only company orgs
SUBSCRIPTION_NOTICE_AFTER = datetime.timedelta(days=7)
"""How long to wait before first reminding owners that a subscription is required."""
SUBSCRIPTION_NOTICE_INTERVAL = datetime.timedelta(days=30)
"""Minimum time between subscription requirement reminder emails for corpos types."""

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
