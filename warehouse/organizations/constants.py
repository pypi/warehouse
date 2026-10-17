# SPDX-License-Identifier: Apache-2.0

"""Constants related to PyPI organizations."""

import datetime

CLEANUP_AFTER = datetime.timedelta(days=30)
"""How long to keep declined organization applications before deletion."""

## -- Things rleating to only company orgs
SUBSCRIPTION_NOTICE_AFTER = datetime.timedelta(days=7)
"""How long to wait before first reminding owners that a subscription is required."""
DEACTIVATION_NOTICE_DAYS = (30, 14, 3)
"""Days before deactivation that we email owners of an unpaid Company org."""
