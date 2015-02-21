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

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound

from warehouse.packaging.views import project_detail

from ..common.db.accounts import UserFactory
from ..common.db.packaging import ProjectFactory, ReleaseFactory, RoleFactory


class TestProjectDetail:

    @pytest.mark.parametrize("version", [None, "1.0"])
    def test_missing_project(self, db_request, version):
        project = ProjectFactory.create(session=db_request.db)

        with pytest.raises(HTTPNotFound):
            project_detail(
                db_request, name=project.name + "nope", version=version,
            )

    @pytest.mark.parametrize("version", [None, "1.0"])
    def test_normalizing_redirects(self, db_request, version):
        project = ProjectFactory.create(session=db_request.db)

        name = project.name.lower()
        if name == project.name:
            name = project.name.upper()

        db_request.current_route_url = pretend.call_recorder(
            lambda name: "/project/the-redirect/"
        )

        resp = project_detail(db_request, name=name, version=version)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/"
        assert db_request.current_route_url.calls == [
            pretend.call(name=project.name),
        ]

    @pytest.mark.parametrize("version", [None, "1.0"])
    def test_missing_release(self, db_request, version):
        project = ProjectFactory.create(session=db_request.db)

        with pytest.raises(HTTPNotFound):
            project_detail(db_request, name=project.name, version=version)

    @pytest.mark.parametrize(
        ("version", "versions"),
        [
            (None, ["1.0", "2.0", "3.0"]),
            ("2.0", ["1.0", "2.0", "3.0"]),
        ],
    )
    def test_detail_renders(self, db_request, version, versions):
        users = [
            UserFactory.create(session=db_request.db),
            UserFactory.create(session=db_request.db),
            UserFactory.create(session=db_request.db),
        ]
        project = ProjectFactory.create(session=db_request.db)
        releases = [
            ReleaseFactory.create(
                session=db_request.db, project=project, version=v,
            )
            for v in versions
        ]

        # Create a role for each user
        for user in users:
            RoleFactory.create(
                session=db_request.db, user=user, project=project,
            )

        # Add an extra role for one user, to ensure deduplication
        RoleFactory.create(
            session=db_request.db,
            user=users[0],
            project=project,
            role_name="another role",
        )

        daily_stats = pretend.stub()
        weekly_stats = pretend.stub()
        monthly_stats = pretend.stub()

        db_request.find_service = lambda x: pretend.stub(
            get_daily_stats=lambda p: daily_stats,
            get_weekly_stats=lambda p: weekly_stats,
            get_monthly_stats=lambda p: monthly_stats,
        )

        result = project_detail(db_request, name=project.name, version=version)

        latest_version = version if version is not None else versions[-1]

        assert result == {
            "project": project,
            "release": releases[versions.index(latest_version)],
            "all_releases": [
                (r.version, r.created) for r in reversed(releases)
            ],
            "maintainers": sorted(users, key=lambda u: u.username.lower()),
            "download_stats": {
                "daily": daily_stats,
                "weekly": weekly_stats,
                "monthly": monthly_stats,
            },
        }
