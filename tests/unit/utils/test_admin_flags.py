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

from warehouse.utils.admin_flags import AdminFlag

from ...common.db.utils import AdminFlagFactory as DBAdminFlagFactory


class TestAdminFlag:

    def test_default(self, db_session):
        assert not AdminFlag.is_enabled(db_session, 'not-a-real-flag')

    def test_enabled(self, db_session):
        DBAdminFlagFactory.create(id='this-flag-is-enabled', enabled=True)
        assert AdminFlag.is_enabled(db_session, 'this-flag-is-enabled')
