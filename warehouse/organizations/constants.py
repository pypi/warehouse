# SPDX-License-Identifier: Apache-2.0

"""Constants related to PyPI organizations."""

import datetime as dt

CLEANUP_AFTER = dt.timedelta(days=30)
"""How long to keep declined organization applications before deletion."""
UNDEFER_AFTER = dt.timedelta(days=30)
"""How long a deferred organization application waits before returning to review."""

## -- Things rleating to only company orgs
SUBSCRIPTION_NOTICE_AFTER = dt.timedelta(days=7)
"""How long to wait before first reminding owners that a subscription is required."""
DEACTIVATION_NOTICE_DAYS = (30, 14, 3)
"""Days before deactivation that we email owners of an unpaid Company org."""
DEACTIVATION_STARTS_PER_DAY = 500
"""Most unpaid Company orgs whose notice period starts each night."""
DEACTIVATIONS_PER_DAY = 500
"""Most unpaid Company orgs deactivated each night; the rest wait a night."""
REACTIVATE_BY_PAYING_WITHIN = dt.timedelta(days=90)
"""How long after deactivation for no paid seat owners can reactivate by paying."""
RECONCILE_MAX_DOWNGRADES = 10
"""Most subscriptions one reconciliation run may move off a paid status."""

NAME_SIMILARITY_THRESHOLD = 0.6
"""Lowest `difflib` ratio that still reads as the same organization."""

MIN_SUBSTRING_LENGTH = 3
"""Length both names must reach before one containing the other counts as a match.

Below it, `ar` would match `litestar`.
"""
