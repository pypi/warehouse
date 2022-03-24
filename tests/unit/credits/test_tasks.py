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

from warehouse.credits.contributors import Contributor
from warehouse.credits import tasks


from ...common.db.contributors import ContributorFactory


class TestGetContributors:
    def test_add_new_user_success(self, db_request, monkeypatch):

        token = pretend.stub()
        db_request.registry.settings = {
            "warehouse.github_access_token": token,
        }

        # try using ContributorFactory.create()
        users = [ContributorFactory.create() for _ in range(2)]

        contributor = pretend.stub(
            refresh=pretend.call_recorder(lambda: users)
        )
        repo = pretend.stub(
            contributors=pretend.call_recorder(lambda: contributor),
        )
        client = pretend.stub(
            repository=pretend.call_recorder(lambda owner, name: repo),
        )
        login = pretend.call_recorder(lambda token: client)

        monkeypatch.setattr(tasks.github3, 'login', login)

        # add existing contributors to db
        db_request.db.add(
            Contributor(
                contributor_login="someone",
                contributor_name='Some One',
                contributor_url='https://some_url.com'
            )
        )

        tasks.get_contributors(db_request)

        assert login.calls == [
            pretend.call(access_token=token)
        ]

        query2 = db_request.db.query(Contributor).all()

        assert len(query2) == 2
