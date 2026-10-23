# SPDX-License-Identifier: Apache-2.0

import datetime as dt
import enum
import os

ONE_MIB = 1 * 1024 * 1024
ONE_GIB = 1 * 1024 * 1024 * 1024
MAX_FILESIZE = 100 * ONE_MIB
MAX_PROJECT_SIZE = 10 * ONE_GIB
ORGANIZATION_MAX_FILESIZE = (
    int(os.environ.get("ORGANIZATION_MAX_FILESIZE_MIB", 2 * MAX_FILESIZE // ONE_MIB))
    * ONE_MIB
)
"""Default file limit for org-owned projects; env-read since models lack settings."""
ORGANIZATION_MAX_PROJECT_SIZE = (
    int(
        os.environ.get(
            "ORGANIZATION_MAX_PROJECT_SIZE_GIB", 2 * MAX_PROJECT_SIZE // ONE_GIB
        )
    )
    * ONE_GIB
)
"""Default total size limit for org-owned projects; env-read, as above."""
UPLOAD_LIMIT_CAP = ONE_GIB
PROJECT_CREATE_RATELIMIT_CAP = 100
"""The limit for project creations for orgs and users in the admin UI"""
# Taken from passlib
MAX_PASSWORD_SIZE = 4096

# After a release has been published for this long, reject new uploaded files.
MAXIMUM_AGE_FOR_NEW_UPLOADS = dt.timedelta(days=14)


class RateLimitPeriod(enum.StrEnum):
    """The period half of a `limits`-syntax rate limit, e.g. the "hour" in
    "20 per hour".
    """

    Hour = "hour"
    Day = "day"
    Month = "month"
