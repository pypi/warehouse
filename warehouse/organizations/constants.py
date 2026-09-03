"""Constants related to PyPI organizations."""

import datetime

CLEANUP_AFTER = datetime.timedelta(days=30)
"""How long to keep declined organization applications before deletion."""

## -- Things rleating to only company orgs
SUBSCRIPTION_GRACE_PERIOD = datetime.timedelta(days=30)
"""How long company organizations have to add a subscription seat after creation."""
SUBSCRIPTION_NOTICE_AFTER = datetime.timedelta(days=7)
"""How long to wait before first reminding owners that a subscription is required."""
SUBSCRIPTION_NOTICE_INTERVAL = datetime.timedelta(days=30)
"""Minimum time between subscription requirement reminder emails for corpos types."""
