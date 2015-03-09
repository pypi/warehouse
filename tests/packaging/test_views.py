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

from warehouse.packaging import views

from ..common.db.accounts import UserFactory
from ..common.db.packaging import (
    ProjectFactory, ReleaseFactory, FileFactory, RoleFactory,
)


class TestProjectDetail:

    def test_normalizing_redirects(self, db_request):
        project = ProjectFactory.create(session=db_request.db)

        name = project.name.lower()
        if name == project.name:
            name = project.name.upper()

        db_request.matchdict = {"name": name}
        db_request.current_route_url = pretend.call_recorder(
            lambda name: "/project/the-redirect/"
        )

        resp = views.project_detail(project, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/"
        assert db_request.current_route_url.calls == [
            pretend.call(name=project.name),
        ]

    def test_missing_release(self, db_request):
        project = ProjectFactory.create(session=db_request.db)

        with pytest.raises(HTTPNotFound):
            views.project_detail(project, db_request)

    def test_calls_release_detail(self, monkeypatch, db_request):
        project = ProjectFactory.create(session=db_request.db)

        ReleaseFactory.create(
            session=db_request.db, project=project, version="1.0",
        )
        ReleaseFactory.create(
            session=db_request.db, project=project, version="2.0",
        )

        release = ReleaseFactory.create(
            session=db_request.db, project=project, version="3.0",
        )

        response = pretend.stub()
        release_detail = pretend.call_recorder(lambda ctx, request: response)
        monkeypatch.setattr(views, "release_detail", release_detail)

        resp = views.project_detail(project, db_request)

        assert resp is response
        assert release_detail.calls == [pretend.call(release, db_request)]


class TestReleaseDetail:

    def test_normalizing_redirects(self, db_request):
        project = ProjectFactory.create(session=db_request.db)
        release = ReleaseFactory.create(
            session=db_request.db, project=project, version="3.0",
        )

        name = release.project.name.lower()
        if name == release.project.name:
            name = release.project.name.upper()

        db_request.matchdict = {"name": name}
        db_request.current_route_url = pretend.call_recorder(
            lambda name: "/project/the-redirect/3.0/"
        )

        resp = views.release_detail(release, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/3.0/"
        assert db_request.current_route_url.calls == [
            pretend.call(name=release.project.name),
        ]

    def test_detail_renders(self, db_request):
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
            for v in ["1.0", "2.0", "3.0"]
        ]
        files = [
            FileFactory.create(
                session=db_request.db,
                release=r,
                filename="{}-{}.tar.gz".format(project.name, r.version),
                python_version="source",
            )
            for r in releases
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

        result = views.release_detail(releases[1], db_request)

        assert result == {
            "project": project,
            "release": releases[1],
            "files": [files[1]],
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
