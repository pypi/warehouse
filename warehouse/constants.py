# SPDX-License-Identifier: Apache-2.0

import datetime as dt
import enum
import os

ONE_MIB = 1 * 1024 * 1024
ONE_GIB = 1 * 1024 * 1024 * 1024
MAX_FILESIZE = 100 * ONE_MIB
MAX_PROJECT_SIZE = 10 * ONE_GIB
# Defaults for organization-owned projects, configurable per deployment.
ORGANIZATION_MAX_FILESIZE = (
    int(os.environ.get("ORGANIZATION_MAX_FILESIZE_MIB", MAX_FILESIZE // ONE_MIB))
    * ONE_MIB
)
ORGANIZATION_MAX_PROJECT_SIZE = (
    int(
        os.environ.get("ORGANIZATION_MAX_PROJECT_SIZE_GIB", MAX_PROJECT_SIZE // ONE_GIB)
    )
    * ONE_GIB
)
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
