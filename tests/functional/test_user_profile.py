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

from tests.common.db.accounts import UserFactory


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
    assert resp.status_code == 200
