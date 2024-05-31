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

from sqlalchemy import text

from tests.common.db.accounts import UserFactory


def test_user_profile(webtest, db_session):
    user = UserFactory.create()
    assert user.username
    print(f"got user {user.username}", flush=True)
    result = db_session.execute(text("select * from users"))
    actual = ["; ".join([f"{s}" for s in row]) for row in result]
    print(actual, flush=True)
    # visit user's page
    resp = webtest.get(f"/user/{user.username}/")
    assert resp.status_code == 200
