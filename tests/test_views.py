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

from pyramid.testing import DummyRequest

from warehouse.views import index

from ..common.db.packaging import (
    ProjectFactory, ReleaseFactory, FileFactory, RoleFactory,
)
from ..common.db.accounts import UserFactory


class TestIndex:

    def test_index(self, db_request):
        request = DummyRequest()

        project = ProjectFactory.create()
        release1 = ReleaseFactory.create(project=project, version="2.0")
        release2 = ReleaseFactory.create(project=project, version="1.0")
        file_ = FileFactory.create(
            release=release1,
            filename="{}-{}.tar.gz".format(project.name, release1.version),
            python_version="source",
        )
        user = UserFactory.create()

        assert index(request) == {
                                     'latest_updated_releases': [release2, release1],
                                     'num_projects': 1,
                                     'num_users': 1,
                                     'num_releases': 2,
                                     'num_files': 1,
                                 }