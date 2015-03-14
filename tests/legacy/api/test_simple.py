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

from warehouse.legacy.api import simple

from ...common.db.accounts import UserFactory
from ...common.db.packaging import ProjectFactory, JournalEntryFactory


class TestSimpleIndex:

    def test_no_results_no_serial(self, db_request):
        assert simple.simple_index(db_request) == {"projects": []}
        assert db_request.response.headers["X-PyPI-Last-Serial"] == 0

    def test_no_results_with_serial(self, db_request):
        user = UserFactory.create(session=db_request.db)
        je = JournalEntryFactory.create(
            session=db_request.db, submitted_by=user.username,
        )
        assert simple.simple_index(db_request) == {"projects": []}
        assert db_request.response.headers["X-PyPI-Last-Serial"] == je.id

    def test_with_results_no_serial(self, db_request):
        projects = [
            (x.name, x.normalized_name)
            for x in
            [ProjectFactory.create(session=db_request.db) for _ in range(3)]
        ]
        assert simple.simple_index(db_request) == {
            "projects": sorted(projects, key=lambda x: x[1]),
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == 0

    def test_with_results_with_serial(self, db_request):
        projects = [
            (x.name, x.normalized_name)
            for x in
            [ProjectFactory.create(session=db_request.db) for _ in range(3)]
        ]
        user = UserFactory.create(session=db_request.db)
        je = JournalEntryFactory.create(
            session=db_request.db, submitted_by=user.username,
        )

        assert simple.simple_index(db_request) == {
            "projects": sorted(projects, key=lambda x: x[1]),
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == je.id
