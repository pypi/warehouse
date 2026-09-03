# SPDX-License-Identifier: Apache-2.0

import datetime

ONE_MIB = 1 * 1024 * 1024
ONE_GIB = 1 * 1024 * 1024 * 1024
MAX_FILESIZE = 100 * ONE_MIB
MAX_PROJECT_SIZE = 10 * ONE_GIB
UPLOAD_LIMIT_CAP = ONE_GIB
# Taken from passlib
MAX_PASSWORD_SIZE = 4096

# After a release has been published for this long, reject new uploaded files.
MAXIMUM_AGE_FOR_NEW_UPLOADS = datetime.timedelta(days=14)
