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

import io

import pretend

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from webob import datetime_utils

from warehouse.packaging import views
from warehouse.packaging.interfaces import IFileStorage

from ...common.db.accounts import UserFactory
from ...common.db.packaging import (
    ProjectFactory, ReleaseFactory, FileFactory, RoleFactory,
)


class TestProjectDetail:

    def test_normalizing_redirects(self, db_request):
        project = ProjectFactory.create()

        name = project.name.lower()
        if name == project.name:
            name = project.name.upper()

        db_request.matchdict = {"name": name}
        db_request.current_route_path = pretend.call_recorder(
            lambda name: "/project/the-redirect/"
        )

        resp = views.project_detail(project, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/"
        assert db_request.current_route_path.calls == [
            pretend.call(name=project.name),
        ]

    def test_missing_release(self, db_request):
        project = ProjectFactory.create()
        resp = views.project_detail(project, db_request)
        assert isinstance(resp, HTTPNotFound)

    def test_calls_release_detail(self, monkeypatch, db_request):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0")
        ReleaseFactory.create(project=project, version="2.0")

        release = ReleaseFactory.create(project=project, version="3.0")

        response = pretend.stub()
        release_detail = pretend.call_recorder(lambda ctx, request: response)
        monkeypatch.setattr(views, "release_detail", release_detail)

        resp = views.project_detail(project, db_request)

        assert resp is response
        assert release_detail.calls == [pretend.call(release, db_request)]


class TestReleaseDetail:

    def test_normalizing_redirects(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="3.0")

        name = release.project.name.lower()
        if name == release.project.name:
            name = release.project.name.upper()

        db_request.matchdict = {"name": name}
        db_request.current_route_path = pretend.call_recorder(
            lambda name: "/project/the-redirect/3.0/"
        )

        resp = views.release_detail(release, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/3.0/"
        assert db_request.current_route_path.calls == [
            pretend.call(name=release.project.name),
        ]

    def test_detail_renders(self, db_request):
        users = [
            UserFactory.create(),
            UserFactory.create(),
            UserFactory.create(),
        ]
        project = ProjectFactory.create()
        releases = [
            ReleaseFactory.create(project=project, version=v)
            for v in ["1.0", "2.0", "3.0"]
        ]
        files = [
            FileFactory.create(
                release=r,
                filename="{}-{}.tar.gz".format(project.name, r.version),
                python_version="source",
            )
            for r in releases
        ]

        # Create a role for each user
        for user in users:
            RoleFactory.create(user=user, project=project)

        # Add an extra role for one user, to ensure deduplication
        RoleFactory.create(
            user=users[0],
            project=project,
            role_name="another role",
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
        }


class TestPackages:

    def test_404_when_no_file(self, db_request):
        db_request.matchdict["path"] = "source/f/foo/foo-1.0.tar.gz"
        resp = views.packages(db_request)
        assert isinstance(resp, HTTPNotFound)

    def test_404_when_no_sig(self, db_request, pyramid_config):
        pyramid_config.registry["filesystems"] = {
            "packages": pretend.stub(exists=lambda p: False),
        }

        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        file_ = FileFactory.create(
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
        )

        db_request.matchdict["path"] = "source/{}/{}/{}.asc".format(
            project.name[0], project.name, file_.filename
        )

        resp = views.packages(db_request)

        assert isinstance(resp, HTTPNotFound)

    def test_404_when_missing_file(self, db_request, pyramid_config):
        @pretend.call_recorder
        def raiser(path):
            raise FileNotFoundError

        storage_service = pretend.stub(get=raiser)

        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        file_ = FileFactory.create(
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
        )

        path = "source/{}/{}/{}".format(
            project.name[0], project.name, file_.filename
        )

        db_request.matchdict["path"] = path
        db_request.log = pretend.stub(
            error=pretend.call_recorder(lambda event, **kw: None),
        )
        db_request.find_service = pretend.call_recorder(
            lambda iface: storage_service
        )

        resp = views.packages(db_request)

        assert isinstance(resp, HTTPNotFound)
        assert db_request.find_service.calls == [pretend.call(IFileStorage)]
        assert storage_service.get.calls == [pretend.call(path)]
        assert db_request.log.error.calls == [
            pretend.call("missing file data", path=path),
        ]

    def test_serves_package_file(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        file_ = FileFactory.create(
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
            size=27,
        )

        path = "source/{}/{}/{}".format(
            project.name[0], project.name, file_.filename
        )

        storage_service = pretend.stub(
            get=pretend.call_recorder(
                lambda path: io.BytesIO(b"some data for the fake file")
            )
        )

        db_request.matchdict["path"] = path
        db_request.find_service = pretend.call_recorder(
            lambda iface: storage_service
        )

        resp = views.packages(db_request)

        # We want to roundtrip our upload_time
        last_modified = datetime_utils.parse_date(
            datetime_utils.serialize_date(file_.upload_time)
        )

        assert db_request.find_service.calls == [pretend.call(IFileStorage)]
        assert storage_service.get.calls == [pretend.call(path)]

        assert resp.content_type == "application/octet-stream"
        assert resp.content_encoding is None
        assert resp.etag == file_.md5_digest
        assert resp.last_modified == last_modified
        assert resp.content_length == 27
        # This needs to be last, as accessing resp.body sets the content_length
        assert resp.body == b"some data for the fake file"

    def test_serves_signature_file(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        file_ = FileFactory.create(
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
            has_signature=True,
        )

        path = "source/{}/{}/{}.asc".format(
            project.name[0], project.name, file_.filename
        )

        storage_service = pretend.stub(
            get=pretend.call_recorder(
                lambda path: io.BytesIO(b"some data for the fake file")
            )
        )

        db_request.matchdict["path"] = path
        db_request.find_service = pretend.call_recorder(
            lambda iface: storage_service
        )

        resp = views.packages(db_request)

        # We want to roundtrip our upload_time
        last_modified = datetime_utils.parse_date(
            datetime_utils.serialize_date(file_.upload_time)
        )

        assert db_request.find_service.calls == [pretend.call(IFileStorage)]
        assert storage_service.get.calls == [pretend.call(path)]

        assert resp.content_type == "application/octet-stream"
        assert resp.content_encoding is None
        assert resp.etag == file_.md5_digest
        assert resp.last_modified == last_modified
        assert resp.content_length is None
        # This needs to be last, as accessing resp.body sets the content_length
        assert resp.body == b"some data for the fake file"
