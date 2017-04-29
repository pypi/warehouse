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

from first import first
from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound

from warehouse.packaging import views

from ...common.db.accounts import UserFactory
from ...common.db.classifiers import ClassifierFactory
from ...common.db.packaging import (
    ProjectFactory, ReleaseFactory, FileFactory, RoleFactory,
)


class TestProjectDetail(object):

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

    def test_with_prereleases(self, monkeypatch, db_request):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0")
        ReleaseFactory.create(project=project, version="2.0")
        ReleaseFactory.create(project=project, version="4.0.dev0")

        release = ReleaseFactory.create(project=project, version="3.0")

        response = pretend.stub()
        release_detail = pretend.call_recorder(lambda ctx, request: response)
        monkeypatch.setattr(views, "release_detail", release_detail)

        resp = views.project_detail(project, db_request)

        assert resp is response
        assert release_detail.calls == [pretend.call(release, db_request)]

    def test_only_prereleases(self, monkeypatch, db_request):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0.dev0")
        ReleaseFactory.create(project=project, version="2.0.dev0")

        release = ReleaseFactory.create(project=project, version="3.0.dev0")

        response = pretend.stub()
        release_detail = pretend.call_recorder(lambda ctx, request: response)
        monkeypatch.setattr(views, "release_detail", release_detail)

        resp = views.project_detail(project, db_request)

        assert resp is response
        assert release_detail.calls == [pretend.call(release, db_request)]


class TestReleaseDetail(object):

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
            for v in ["1.0", "2.0", "3.0", "4.0.dev0"]
        ]
        latest_release = first(
            reversed(releases),
            key=lambda r: not r.is_prerelease,
        )
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
            "latest_release": (
                latest_release.version,
                latest_release.is_prerelease,
                latest_release.created,
            ),
            "all_releases": [
                (r.version, r.is_prerelease, r.created)
                for r in reversed(releases)
            ],
            "maintainers": sorted(users, key=lambda u: u.username.lower()),
            "license": None
        }

    def test_license_from_classifier(self, db_request):
        """A license label is added when a license classifier exists."""
        other_classifier = ClassifierFactory.create(
            classifier="Some :: Random :: Classifier")
        classifier = ClassifierFactory.create(
            classifier="License :: OSI Approved :: BSD License")
        release = ReleaseFactory.create(
            _classifiers=[other_classifier, classifier],
            license="Will not be used")

        result = views.release_detail(release, db_request)

        assert result["license"] == "BSD License"

    def test_license_with_no_classifier(self, db_request):
        """With no classifier, a license is used from metadata."""
        release = ReleaseFactory.create(license="MIT License")

        result = views.release_detail(release, db_request)

        assert result["license"] == "MIT License"

    def test_multiline_license(self, db_request):
        """When license metadata is longer than one line, the first is used."""
        release = ReleaseFactory.create(
            license="Multiline License\nhow terrible")

        result = views.release_detail(release, db_request)

        assert result["license"] == "Multiline License"

    def test_no_license(self, db_request):
        """With no license classifier or metadata, no license is in context."""
        release = ReleaseFactory.create()

        result = views.release_detail(release, db_request)

        assert result["license"] is None

    def test_multiple_licenses_from_classifiers(self, db_request):
        """A license label is added when multiple license classifiers exist."""
        license_1 = ClassifierFactory.create(
            classifier="License :: OSI Approved :: BSD License")
        license_2 = ClassifierFactory.create(
            classifier="License :: OSI Approved :: MIT License")
        release = ReleaseFactory.create(_classifiers=[license_1, license_2])

        result = views.release_detail(release, db_request)

        assert result["license"] == "BSD License, MIT License"
