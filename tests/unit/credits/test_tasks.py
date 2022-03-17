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
import pytest

from warehouse.credits.contributors import Contributor
from warehouse.credits import tasks


from ...common.db.contributors import ContributorFactory

class TestGetContributors:
    # @pytest.mark.parametrize("with_github_access_token", [True, False])
    def test_add_new_user_success(self, db_request, monkeypatch):

        token = pretend.stub()
        db_request.registry.settings = {
            "warehouse.github_access_token": token,
        }

        contributors = [
            pretend.stub(
                login="gvanrossum",
                html_url="https://github.com/gvanrossum"
            ),
        ]
        users = pretend.stub(
            name="Guido van Rossum",
            login="gvanrossum",
            html_url="https://github.com/gvanrossum"
        )

        repo = pretend.stub(
            contributors=pretend.call_recorder(lambda: contributors)
        )
        client = pretend.stub(
            repository=pretend.call_recorder(lambda owner, name: repo),
            user=pretend.call_recorder(lambda c: users)
        )
        login=pretend.call_recorder(lambda token: client)

        monkeypatch.setattr(tasks.github3, 'login', login)

        # need to create a fixture of contributors which are in the database already here
        # to mock the request.db_query() that occurs on line 66

        # new_users here needs to be a list of users not in the db that are in the contributors dict above

        # handle query2 on line 86

        # figure out how to handle the bulk_save_objects() call on line 91

        # set the existing contributors
        existing_contributors = ContributorFactory.create(contributor_login="someone",
                                                          contributor_name='Some One',
                                                          contributor_url='https://some_url.com')

        # find better name
        blah = pretend.stub(
            all=pretend.call_recorder(lambda id, contributor_login, name, url: existing_contributors)
        )

        # db_request.db.query = pretend.call_recorder(lambda id, login, name, url: existing_contributors)
        db_request.db.query = blah
        # monkeypatch.setattr(tasks.request.db.query, "all", blah)

        tasks.get_contributors(db_request)

        assert github3.login.calls == [
            pretend.call(access_token=token)
        ]


        # assert db_request.db.query(Contributor).all() == [

        # ]
        # more assertions on call recorders

# TODO
#
# def test_add_new_user_failure(self, db_request, monkeypatch):
#     pass
#
# def test_update_existing_user_success(self, db_request, monkeypatch):
#     pass
#
# def test_update_existing_user_failure(self, db_request, monkeypatch):
#     pass
