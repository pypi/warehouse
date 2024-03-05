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

from natsort import natsorted
from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound

from warehouse.packaging import views
from warehouse.utils import readme

from ...common.db.accounts import UserFactory
from ...common.db.classifiers import ClassifierFactory
from ...common.db.packaging import (
    DescriptionFactory,
    FileFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
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
        assert db_request.current_route_path.calls == [pretend.call(name=project.name)]

    def test_missing_release(self, db_request):
        project = ProjectFactory.create()

        with pytest.raises(HTTPNotFound):
            views.project_detail(project, db_request)

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

    def test_prefers_non_yanked_release(self, monkeypatch, db_request):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="2.0", yanked=True)
        release = ReleaseFactory.create(project=project, version="1.0")

        response = pretend.stub()
        release_detail = pretend.call_recorder(lambda ctx, request: response)
        monkeypatch.setattr(views, "release_detail", release_detail)

        resp = views.project_detail(project, db_request)

        assert resp is response
        assert release_detail.calls == [pretend.call(release, db_request)]

    def test_only_yanked_release(self, monkeypatch, db_request):
        project = ProjectFactory.create()

        release = ReleaseFactory.create(project=project, version="1.0", yanked=True)

        response = pretend.stub()
        release_detail = pretend.call_recorder(lambda ctx, request: response)
        monkeypatch.setattr(views, "release_detail", release_detail)

        resp = views.project_detail(project, db_request)

        assert resp is response
        assert release_detail.calls == [pretend.call(release, db_request)]


class TestReleaseDetail:
    def test_normalizing_name_redirects(self, db_request):
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
            pretend.call(name=release.project.name)
        ]

    def test_normalizing_version_redirects(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="3.0")

        db_request.matchdict = {"name": project.name, "version": "3.0.0.0.0"}
        db_request.current_route_path = pretend.call_recorder(
            lambda **kw: "/project/the-redirect/3.0/"
        )

        resp = views.release_detail(release, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/3.0/"
        assert db_request.current_route_path.calls == [
            pretend.call(name=release.project.name, version=release.version)
        ]

    def test_detail_render_plain(self, db_request):
        users = [UserFactory.create(), UserFactory.create(), UserFactory.create()]
        project = ProjectFactory.create()
        releases = [
            ReleaseFactory.create(
                project=project,
                version=v,
                description=DescriptionFactory.create(
                    raw="plaintext description",
                    html="",
                    content_type="text/plain",
                ),
            )
            for v in ["1.0", "2.0", "3.0", "4.0.dev0"]
        ] + [
            ReleaseFactory.create(
                project=project,
                version="5.0",
                description=DescriptionFactory.create(
                    raw="plaintext description",
                    html="",
                    content_type="text/plain",
                ),
                yanked=True,
                yanked_reason="plaintext yanked reason",
            )
        ]
        files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.tar.gz",
                python_version="source",
                packagetype="sdist",
            )
            for r in releases
        ]

        # Create a role for each user
        for user in users:
            RoleFactory.create(user=user, project=project)

        result = views.release_detail(releases[1], db_request)

        assert result == {
            "project": project,
            "release": releases[1],
            "files": [files[1]],
            "sdists": [files[1]],
            "bdists": [],
            "description": "<pre>plaintext description</pre>",
            "latest_version": project.latest_version,
            "all_versions": [
                (r.version, r.created, r.is_prerelease, r.yanked, r.yanked_reason)
                for r in reversed(releases)
            ],
            "maintainers": sorted(users, key=lambda u: u.username.lower()),
            "license": None,
        }

    def test_detail_rendered(self, db_request):
        users = [UserFactory.create(), UserFactory.create(), UserFactory.create()]
        project = ProjectFactory.create()
        releases = [
            ReleaseFactory.create(
                project=project,
                version=v,
                description=DescriptionFactory.create(
                    raw="unrendered description",
                    html="rendered description",
                    content_type="text/html",
                ),
            )
            for v in ["1.0", "2.0", "3.0", "4.0.dev0"]
        ] + [
            ReleaseFactory.create(
                project=project,
                version="5.0",
                description=DescriptionFactory.create(
                    raw="plaintext description",
                    html="",
                    content_type="text/plain",
                ),
                yanked=True,
                yanked_reason="plaintext yanked reason",
            )
        ]
        files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.tar.gz",
                python_version="source",
                packagetype="sdist",
            )
            for r in releases
        ]

        # Create a role for each user
        for user in users:
            RoleFactory.create(user=user, project=project)

        result = views.release_detail(releases[1], db_request)

        assert result == {
            "project": project,
            "release": releases[1],
            "files": [files[1]],
            "sdists": [files[1]],
            "bdists": [],
            "description": "rendered description",
            "latest_version": project.latest_version,
            "all_versions": [
                (r.version, r.created, r.is_prerelease, r.yanked, r.yanked_reason)
                for r in reversed(releases)
            ],
            "maintainers": sorted(users, key=lambda u: u.username.lower()),
            "license": None,
        }

    def test_detail_renders(self, monkeypatch, db_request):
        users = [UserFactory.create(), UserFactory.create(), UserFactory.create()]
        project = ProjectFactory.create()
        releases = [
            ReleaseFactory.create(
                project=project,
                version=v,
                description=DescriptionFactory.create(
                    raw="unrendered description", html="", content_type="text/html"
                ),
            )
            for v in ["1.0", "2.0", "3.0", "4.0.dev0"]
        ] + [
            ReleaseFactory.create(
                project=project,
                version="5.0",
                description=DescriptionFactory.create(
                    raw="plaintext description",
                    html="",
                    content_type="text/plain",
                ),
                yanked=True,
                yanked_reason="plaintext yanked reason",
            )
        ]
        files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.tar.gz",
                python_version="source",
                packagetype="sdist",
            )
            for r in releases
        ]

        # Create a role for each user
        for user in users:
            RoleFactory.create(user=user, project=project)

        # patch the readme rendering logic.
        render_description = pretend.call_recorder(
            lambda raw, content_type: "rendered description"
        )
        monkeypatch.setattr(readme, "render", render_description)

        result = views.release_detail(releases[1], db_request)

        assert result == {
            "project": project,
            "release": releases[1],
            "files": [files[1]],
            "sdists": [files[1]],
            "bdists": [],
            "description": "rendered description",
            "latest_version": project.latest_version,
            "all_versions": [
                (r.version, r.created, r.is_prerelease, r.yanked, r.yanked_reason)
                for r in reversed(releases)
            ],
            "maintainers": sorted(users, key=lambda u: u.username.lower()),
            "license": None,
        }

        assert render_description.calls == [
            pretend.call("unrendered description", "text/html")
        ]

    def test_detail_renders_files_natural_sort(self, db_request):
        """Tests that when a release has multiple versions of Python,
        the sort order is most recent Python version first."""
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="3.0")
        files = [
            FileFactory.create(
                release=release,
                filename=f"{project.name}-{release.version}-{py_ver}.whl",
                python_version="py2.py3",
                packagetype="bdist_wheel",
            )
            for py_ver in ["cp27", "cp310", "cp39"]  # intentionally out of order
        ]
        sorted_files = natsorted(files, reverse=True, key=lambda f: f.filename)

        result = views.release_detail(release, db_request)

        assert result["files"] == sorted_files

    def test_license_from_classifier(self, db_request):
        """A license label is added when a license classifier exists."""
        other_classifier = ClassifierFactory.create(
            classifier="Some :: Random :: Classifier"
        )
        classifier = ClassifierFactory.create(
            classifier="License :: OSI Approved :: BSD License"
        )
        release = ReleaseFactory.create(
            _classifiers=[other_classifier, classifier],
            license="Will be added at the end",
        )

        result = views.release_detail(release, db_request)

        assert result["license"] == "BSD License (Will be added at the end)"

    def test_license_with_no_classifier(self, db_request):
        """With no classifier, a license is used from metadata."""
        release = ReleaseFactory.create(license="MIT License")

        result = views.release_detail(release, db_request)

        assert result["license"] == "MIT License"

    def test_multiline_license(self, db_request):
        """When license metadata is longer than one line, the first is used."""
        release = ReleaseFactory.create(license="Multiline License\nhow terrible")

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
            classifier="License :: OSI Approved :: BSD License"
        )
        license_2 = ClassifierFactory.create(
            classifier="License :: OSI Approved :: MIT License"
        )
        release = ReleaseFactory.create(_classifiers=[license_1, license_2])

        result = views.release_detail(release, db_request)

        assert result["license"] == "BSD License, MIT License"

    def test_long_singleline_license(self, db_request):
        """When license metadata contains no newlines, it gets truncated"""
        release = ReleaseFactory.create(
            license="Multiline License is very long, so long that it is far longer than"
            " 100 characters, it's really so long, how terrible"
        )

        result = views.release_detail(release, db_request)

        assert result["license"] == (
            "Multiline License is very long, so long that it is far longer than 100 "
            "characters, it's really so lo..."
        )


class TestProjectSubmitMalwareObservation:
    def test_get_render_form(self, pyramid_request):
        project = pretend.stub()
        form_obj = pretend.stub()
        form_class = pretend.call_recorder(lambda d, **kw: form_obj)

        result = views.submit_malware_observation(
            project, pyramid_request, _form_class=form_class
        )

        assert result == {"project": project, "form": form_obj}
        assert form_class.calls == [pretend.call(pyramid_request.POST)]

    def test_post_invalid_form(self, pyramid_request):
        project = pretend.stub()
        form_obj = pretend.stub()
        form_obj.validate = pretend.call_recorder(lambda: False)
        form_class = pretend.call_recorder(lambda d, **kw: form_obj)

        pyramid_request.method = "POST"

        result = views.submit_malware_observation(
            project, pyramid_request, _form_class=form_class
        )

        assert result == {"project": project, "form": form_obj}
        assert form_obj.validate.calls == [pretend.call()]

    def test_post_valid_form(self, db_request):
        user = UserFactory.create()
        project = ProjectFactory.create()
        form_obj = pretend.stub()
        form_obj.inspector_link = pretend.stub(
            data=f"https://inspector.pypi.io/project/{project.name}/"
        )
        form_obj.summary = pretend.stub(data="Bad stuff in here")
        form_obj.validate = pretend.call_recorder(lambda: True)
        form_class = pretend.call_recorder(lambda d, **kw: form_obj)

        db_request.method = "POST"
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: f"/project/{project.name}/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user = user

        result = views.submit_malware_observation(
            project, db_request, _form_class=form_class
        )

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == f"/project/{project.name}/"
        assert form_obj.validate.calls == [pretend.call()]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Your report has been recorded. Thank you for your help.",
                queue="success",
            )
        ]
        assert db_request.route_path.calls == [
            pretend.call("packaging.project", name=project.name)
        ]
        assert len(project.observations) == 1


class TestEditProjectButton:
    def test_edit_project_button_returns_project(self):
        project = pretend.stub()
        assert views.edit_project_button(project, pretend.stub()) == {
            "project": project
        }
