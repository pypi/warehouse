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

import pretend

from warehouse.admin.views import includes

from ....common.db.packaging import ProjectFactory


def test_administer_project_include_returns_project(db_request):
    project = ProjectFactory.create()
    db_request.matchdict = {"project_name": project.name}
    assert includes.administer_project_include(db_request) == {
        "project": project,
        "prohibited": None,
        "project_name": project.name,
        "collisions": [],
    }


def test_administer_user_include_returns_user():
    user = pretend.stub()
    assert includes.administer_user_include(user, pretend.stub()) == {"user": user}
