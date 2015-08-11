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

import datetime

import pretend

from warehouse.views import notfound, forbidden, index

from ..common.db.packaging import (
    ProjectFactory, ReleaseFactory, FileFactory,
)
from ..common.db.accounts import UserFactory


class TestForbiddenView:

    def test_logged_in_returns_empty_context(self):
        exc, request = pretend.stub(), pretend.stub(authenticated_userid=1)
        resp = forbidden(exc, request)
        assert resp == {}

    def test_logged_out_redirects_login(self):
        exc = pretend.stub()
        request = pretend.stub(
            authenticated_userid=None,
            path_qs="/foo/bar/?b=s",
            route_url=pretend.call_recorder(
                lambda route, _query: "/accounts/login/?next=/foo/bar/%3Fb%3Ds"
            ),
        )

        resp = forbidden(exc, request)

        assert resp.status_code == 303
        assert resp.headers["Location"] == \
            "/accounts/login/?next=/foo/bar/%3Fb%3Ds"


class TestNotFoundView:

    def test_returns_empty_context(self):
        exc, request = pretend.stub(), pretend.stub()
        resp = notfound(exc, request)
        assert resp == {}


class TestIndex:

    def test_index(self, db_request):

        project = ProjectFactory.create()
        release1 = ReleaseFactory.create(project=project)
        release1.created = datetime.date(2011, 1, 1)
        release2 = ReleaseFactory.create(project=project)
        release2.created = datetime.date(2012, 1, 1)
        FileFactory.create(
            release=release1,
            filename="{}-{}.tar.gz".format(project.name, release1.version),
            python_version="source",
        )
        UserFactory.create()

        assert index(db_request) == {
            # assert that ordering is correct
            'latest_updated_releases': [release2, release1],
            'num_projects': 1,
            'num_users': 1,
            'num_releases': 2,
            'num_files': 1,
        }
