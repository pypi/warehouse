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

import enum

from ...common.db.admin import AdminFlagFactory


class TestAdminFlagValues(enum.Enum):
    NOT_A_REAL_FLAG = "not-a-real-flag"
    THIS_FLAG_IS_ENABLED = "this-flag-is-enabled"


class TestAdminFlag:
    def test_default(self, db_request):
        assert not db_request.flags.enabled(TestAdminFlagValues.NOT_A_REAL_FLAG)

    def test_enabled(self, db_request):
        AdminFlagFactory(id="this-flag-is-enabled")

        assert db_request.flags.enabled(TestAdminFlagValues.THIS_FLAG_IS_ENABLED)
