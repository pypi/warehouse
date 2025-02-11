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

from http import HTTPStatus

from tests.common.db.accounts import UserFactory
from tests.common.db.packaging import ProjectFactory, ReleaseFactory, RoleFactory
from warehouse.packaging.models import LifecycleStatus


def test_user_profile(webtest):
    """
    This test is maintained as a POC for future tests that want to add data to
    the database and test HTTP endpoints afterwards.

    The trick is to use the ``webtest`` fixture which will create a special
    instance of the Warehouse WSGI app, sharing the same DB session as is active
    in pytest.
    """
    # Create a user
    user = UserFactory.create()
    assert user.username
    # ...and verify that the user's profile page exists
    resp = webtest.get(f"/user/{user.username}/")
    assert resp.status_code == HTTPStatus.OK


def test_user_profile_project_states(webtest):
    user = UserFactory.create()

    # Create some live projects
    projects = ProjectFactory.create_batch(3)
    for project in projects:
        RoleFactory.create(user=user, project=project)
        ReleaseFactory.create(project=project)

    # Create an archived project
    archived_project = ProjectFactory.create(lifecycle_status=LifecycleStatus.Archived)
    RoleFactory.create(user=user, project=archived_project)
    ReleaseFactory.create(project=archived_project)

    resp = webtest.get(f"/user/{user.username}/")

    assert resp.status_code == HTTPStatus.OK
    assert "4 projects" in resp.html.h2.text
