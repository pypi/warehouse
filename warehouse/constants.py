# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import timedelta

ONE_MIB = 1 * 1024 * 1024
ONE_GIB = 1 * 1024 * 1024 * 1024
MAX_FILESIZE = 100 * ONE_MIB
MAX_PROJECT_SIZE = 10 * ONE_GIB

# Time durations, in seconds, as a float
FIVE_MINUTES_IN_SECONDS = timedelta(minutes=5).total_seconds()
TEN_MINUTES_IN_SECONDS = timedelta(minutes=10).total_seconds()
FIFTEEN_MINUTES_IN_SECONDS = timedelta(minutes=15).total_seconds()
THIRTY_MINUTES_IN_SECONDS = timedelta(minutes=30).total_seconds()
ONE_HOUR_IN_SECONDS = timedelta(hours=1).total_seconds()
SIX_HOURS_IN_SECONDS = timedelta(hours=6).total_seconds()
TWELVE_HOURS_IN_SECONDS = timedelta(hours=12).total_seconds()
ONE_DAY_IN_SECONDS = timedelta(days=1).total_seconds()
TWENTY_FIVE_HOURS_IN_SECONDS = timedelta(hours=25).total_seconds()
TWO_DAYS_IN_SECONDS = timedelta(days=2).total_seconds()
THREE_DAYS_IN_SECONDS = timedelta(days=3).total_seconds()
FIVE_DAYS_IN_SECONDS = timedelta(days=5).total_seconds()
TEN_YEARS_IN_SECONDS = timedelta(days=365 * 10).total_seconds()
