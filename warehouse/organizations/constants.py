# SPDX-License-Identifier: Apache-2.0

"""Constants related to PyPI organizations."""

import datetime as dt

CLEANUP_AFTER = dt.timedelta(days=30)
"""How long to keep declined organization applications before deletion."""

## -- Things rleating to only company orgs
SUBSCRIPTION_NOTICE_AFTER = dt.timedelta(days=7)
"""How long to wait before first reminding owners that a subscription is required."""
SUBSCRIPTION_NOTICE_INTERVAL = dt.timedelta(days=30)
"""Minimum time between subscription requirement reminder emails for corpos types."""
REACTIVATE_BY_PAYING_WITHIN = dt.timedelta(days=90)
"""How long after deactivation for no paid seat owners can reactivate by paying."""
