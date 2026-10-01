# SPDX-License-Identifier: Apache-2.0

import types

import pypi_attestations
import pytest

from natsort import natsorted
from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from webob.multidict import MultiDict

from warehouse.constants import MAXIMUM_AGE_FOR_NEW_UPLOADS
from warehouse.packaging import views
from warehouse.packaging.forms import SubmitMalwareObservationForm
from warehouse.packaging.models import LifecycleStatus

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
    @pytest.fixture
    def release_detail(self, mocker):
        """Patch the inner view that ``project_detail`` delegates to."""
        return mocker.patch.object(
            views,
            "release_detail",
            autospec=True,
            return_value=mocker.sentinel.response,
        )

    def test_normalizing_redirects(self, db_request, mocker):
        project = ProjectFactory.create()

        db_request.matchdict = {"name": project.name.swapcase()}
        current_route_path = mocker.patch.object(
            db_request,
            "current_route_path",
            autospec=True,
            return_value="/project/the-redirect/",
        )

        resp = views.project_detail(project, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/"
        current_route_path.assert_called_once_with(name=project.name)

    def test_missing_release(self, db_request):
        project = ProjectFactory.create()

        with pytest.raises(HTTPNotFound):
            views.project_detail(project, db_request)

    def test_calls_release_detail(self, db_request, release_detail):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0")
        ReleaseFactory.create(project=project, version="2.0")

        release = ReleaseFactory.create(project=project, version="3.0")

        resp = views.project_detail(project, db_request)

        assert resp is release_detail.return_value
        release_detail.assert_called_once_with(release, db_request)

    def test_with_prereleases(self, db_request, release_detail):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0")
        ReleaseFactory.create(project=project, version="2.0")
        ReleaseFactory.create(project=project, version="4.0.dev0")

        release = ReleaseFactory.create(project=project, version="3.0")

        resp = views.project_detail(project, db_request)

        assert resp is release_detail.return_value
        release_detail.assert_called_once_with(release, db_request)

    def test_only_prereleases(self, db_request, release_detail):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0.dev0")
        ReleaseFactory.create(project=project, version="2.0.dev0")

        release = ReleaseFactory.create(project=project, version="3.0.dev0")

        resp = views.project_detail(project, db_request)

        assert resp is release_detail.return_value
        release_detail.assert_called_once_with(release, db_request)

    def test_prefers_non_yanked_release(self, db_request, release_detail):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="2.0", yanked=True)
        release = ReleaseFactory.create(project=project, version="1.0")

        resp = views.project_detail(project, db_request)

        assert resp is release_detail.return_value
        release_detail.assert_called_once_with(release, db_request)

    def test_only_yanked_release(self, db_request, release_detail):
        project = ProjectFactory.create()

        release = ReleaseFactory.create(project=project, version="1.0", yanked=True)

        resp = views.project_detail(project, db_request)

        assert resp is release_detail.return_value
        release_detail.assert_called_once_with(release, db_request)

    def test_prefers_non_quarantined_release(self, db_request, release_detail):
        project = ProjectFactory.create()

        ReleaseFactory.create(
            project=project,
            version="2.0",
            lifecycle_status=LifecycleStatus.QuarantineEnter,
        )
        release = ReleaseFactory.create(project=project, version="1.0")

        resp = views.project_detail(project, db_request)

        assert resp is release_detail.return_value
        release_detail.assert_called_once_with(release, db_request)

    def test_only_quarantined_release(self, db_request, release_detail):
        project = ProjectFactory.create()

        release = ReleaseFactory.create(
            project=project,
            version="1.0",
            lifecycle_status=LifecycleStatus.QuarantineEnter,
        )

        resp = views.project_detail(project, db_request)

        assert resp is release_detail.return_value
        release_detail.assert_called_once_with(release, db_request)

    def test_with_staged(self, monkeypatch, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        ReleaseFactory.create(project=project, version="1.1", published=False)

        response = pretend.stub()
        release_detail = pretend.call_recorder(lambda ctx, request: response)
        monkeypatch.setattr(views, "release_detail", release_detail)

        resp = views.project_detail(project, db_request)
        assert resp is response
        assert release_detail.calls == [pretend.call(release, db_request)]


class TestReleaseDetail:
    def test_normalizing_name_redirects(self, db_request, mocker):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="3.0")

        db_request.matchdict = {"name": project.name.swapcase()}
        current_route_path = mocker.patch.object(
            db_request,
            "current_route_path",
            autospec=True,
            return_value="/project/the-redirect/3.0/",
        )

        resp = views.release_detail(release, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/3.0/"
        current_route_path.assert_called_once_with(name=release.project.name)

    def test_normalizing_version_redirects(self, db_request, mocker):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="3.0")

        db_request.matchdict = {"name": project.name, "version": "3.0.0.0.0"}
        current_route_path = mocker.patch.object(
            db_request,
            "current_route_path",
            autospec=True,
            return_value="/project/the-redirect/3.0/",
        )

        resp = views.release_detail(release, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/3.0/"
        current_route_path.assert_called_once_with(
            name=release.project.name, version=release.version
        )

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

        # Add a staged version
        staged_release = ReleaseFactory.create(
            project=project,
            version="5.1",
            description=DescriptionFactory.create(
                raw="unrendered description",
                html="rendered description",
                content_type="text/html",
            ),
            published=False,
        )

        files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.tar.gz",
                python_version="source",
                packagetype="sdist",
            )
            for r in releases + [staged_release]
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
            # Non published version are not listed here
            "all_versions": [
                (
                    r.version,
                    r.created,
                    r.is_prerelease,
                    r.yanked,
                    r.yanked_date,
                    r.yanked_reason,
                    r.lifecycle_status,
                    r.lifecycle_status_changed,
                )
                for r in reversed(releases)
            ],
            "maintainers": sorted(users, key=lambda u: u.username.lower()),
            "license": None,
            "PEP740AttestationViewer": views.PEP740AttestationViewer,
            "wheel_filters_all": {
                "interpreter": {},
                "abi": {},
                "platform": {},
                "other": {},
            },
            "maximum_age_for_new_uploads_days": MAXIMUM_AGE_FOR_NEW_UPLOADS.days,
        }

    def test_detail_renders_files_natural_sort(self, db_request):
        """Tests that when a release has multiple versions of Python,
        the sort order is most recent Python version first."""
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="3.0")
        files = [
            FileFactory.create(
                release=release,
                filename=f"{project.name}-{release.version}-{py_ver}-{py_abi}-{py_platform}"
                ".whl",
                python_version="py2.py3",
                packagetype="bdist_wheel",
            )
            for py_ver in ["cp27", "cp310", "cp39"]  # intentionally out of order
            for py_abi in ["none"]
            for py_platform in ["any"]
        ]
        sorted_files = natsorted(files, reverse=True, key=lambda f: f.filename)

        result = views.release_detail(release, db_request)

        assert result["files"] == sorted_files
        assert [file.wheel_filters for file in result["files"]] == [
            {
                "interpreter": {"cp310": "CPython 3.10"},
                "abi": {"none": "none"},
                "platform": {"any": "any"},
                "other": {},
            },
            {
                "interpreter": {"cp39": "CPython 3.9"},
                "abi": {"none": "none"},
                "platform": {"any": "any"},
                "other": {},
            },
            {
                "interpreter": {"cp27": "CPython 2.7"},
                "abi": {"none": "none"},
                "platform": {"any": "any"},
                "other": {},
            },
        ]

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

    def test_created_with_published(self, db_request):
        release = ReleaseFactory.create()
        assert release.published is True


class TestPEP740AttestationViewer:
    @pytest.fixture
    def gitlab_attestation(self, gitlab_provenance):
        return gitlab_provenance.attestation_bundles[0].attestations[0]

    @pytest.fixture
    def github_attestation(self, github_provenance):
        return github_provenance.attestation_bundles[0].attestations[0]

    def test_github_pep740(self, github_attestation):
        github_publisher = pypi_attestations.GitHubPublisher(
            repository="pypa/sampleproject",
            workflow=".github/workflows/release.yml",
        )

        viewer = views.PEP740AttestationViewer(
            publisher=github_publisher,
            attestation=github_attestation,
        )

        assert viewer.statement_type == "https://in-toto.io/Statement/v1"
        assert viewer.predicate_type == "https://docs.pypi.org/attestations/publish/v1"
        assert viewer.subject_name == "sampleproject-4.0.0.tar.gz"
        assert (
            viewer.subject_digest
            == "0ace7980f82c5815ede4cd7bf9f6693684cec2ae47b9b7ade9add533b8627c6b"
        )
        assert viewer.transparency_entry["integratedTime"] == "1730932627"

        assert viewer.repository_url == "https://github.com/pypa/sampleproject"
        assert viewer.workflow_filename == ".github/workflows/release.yml"
        assert viewer.workflow_url == (
            "https://github.com/pypa/sampleproject/blob/"
            "621e4974ca25ce531773def586ba3ed8e736b3fc/"
            ".github/workflows/release.yml"
        )
        assert viewer.build_digest == "621e4974ca25ce531773def586ba3ed8e736b3fc"

        assert viewer.issuer == "https://token.actions.githubusercontent.com"
        assert viewer.environment == "github-hosted"

        assert viewer.source == "https://github.com/pypa/sampleproject"
        assert viewer.source_digest == "621e4974ca25ce531773def586ba3ed8e736b3fc"
        assert viewer.source_reference == "refs/heads/main"
        assert viewer.owner == "https://github.com/pypa"

        assert viewer.trigger == "push"
        assert viewer.access == "public"
        assert viewer.run_invocation_uri == (
            "https://github.com/pypa/sampleproject/actions/runs/11713038981/attempts/1"
        )

        assert viewer.permalink_with_digest == (
            "https://github.com/pypa/sampleproject/tree/"
            "621e4974ca25ce531773def586ba3ed8e736b3fc"
        )
        assert (
            viewer.permalink_with_reference
            == "https://github.com/pypa/sampleproject/tree/refs/heads/main"
        )

    def test_gitlab_pep740(self, gitlab_attestation):
        gitlab_publisher = pypi_attestations.GitLabPublisher(
            repository="pep740-example/sampleproject",
            workflow_filepath=".gitlab-ci.yml",
        )

        viewer = views.PEP740AttestationViewer(
            publisher=gitlab_publisher,
            attestation=gitlab_attestation,
        )

        assert viewer.statement_type == "https://in-toto.io/Statement/v1"
        assert viewer.predicate_type == "https://docs.pypi.org/attestations/publish/v1"
        assert viewer.subject_name == "pep740_sampleproject-1.0.0.tar.gz"
        assert (
            viewer.subject_digest
            == "6cdd4a1a0a49aeef47265e7bf8ec1667257b397d34d731dc7b7af349deca1cd8"
        )
        assert viewer.transparency_entry["integratedTime"] == "1732724143"

        assert (
            viewer.repository_url == "https://gitlab.com/pep740-example/sampleproject"
        )
        assert viewer.workflow_filename == ".gitlab-ci.yml"
        assert viewer.workflow_url == (
            "https://gitlab.com/pep740-example/sampleproject/blob/"
            "0b706bbf1b50e7266b33762568566d6ec0f76d69//.gitlab-ci.yml"
        )
        assert viewer.build_digest == "0b706bbf1b50e7266b33762568566d6ec0f76d69"

        assert viewer.issuer == "https://gitlab.com"
        assert viewer.environment == "gitlab-hosted"

        assert viewer.source == "https://gitlab.com/pep740-example/sampleproject"
        assert viewer.source_digest == "0b706bbf1b50e7266b33762568566d6ec0f76d69"
        assert viewer.source_reference == "refs/heads/main"
        assert viewer.owner == "https://gitlab.com/pep740-example"

        assert viewer.trigger == "push"
        assert viewer.access == "private"
        assert viewer.run_invocation_uri == (
            "https://gitlab.com/pep740-example/sampleproject/-/jobs/8486974559"
        )

        assert viewer.permalink_with_digest == (
            "https://gitlab.com/pep740-example/sampleproject/-/tree/"
            "0b706bbf1b50e7266b33762568566d6ec0f76d69"
        )
        assert (
            viewer.permalink_with_reference
            == "https://gitlab.com/pep740-example/sampleproject/-/tree/main"
        )

    def test_unknown_publisher(self, github_attestation):
        viewer = views.PEP740AttestationViewer(
            publisher=types.SimpleNamespace(kind="Unknown"),
            attestation=types.SimpleNamespace(certificate_claims={}),
        )

        assert viewer.workflow_filename == ""
        assert (
            viewer._format_url("https://example.com", "refs/heads/main")
            == "https://example.com/refs/heads/main"
        )


class TestProjectSubmitMalwareObservation:
    def test_get_render_form(self, pyramid_request):
        project = ProjectFactory.build()

        # DummyRequest defaults these to plain dicts, aliased to each other;
        # WTForms needs a multidict
        pyramid_request.GET = MultiDict({"summary": "Bad stuff in here"})
        pyramid_request.POST = MultiDict()

        result = views.submit_malware_observation(project, pyramid_request)

        assert result["project"] is project
        assert isinstance(result["form"], SubmitMalwareObservationForm)
        # the rendered form is fed from GET, which is what prefills it
        assert result["form"].summary.data == "Bad stuff in here"

    def test_post_invalid_form(self, pyramid_request):
        project = ProjectFactory.build()

        pyramid_request.method = "POST"
        pyramid_request.GET = MultiDict()
        pyramid_request.POST = MultiDict({"inspector_link": "", "summary": ""})

        result = views.submit_malware_observation(project, pyramid_request)

        assert result["project"] is project
        assert result["form"].errors

    def test_post_valid_form(self, db_request, mocker):
        user = UserFactory.create()
        project = ProjectFactory.create()

        db_request.method = "POST"
        db_request.GET = MultiDict()
        db_request.POST = MultiDict(
            {
                "inspector_link": f"https://inspector.pypi.io/project/{project.name}/",
                "summary": "Bad stuff in here",
            }
        )
        db_request.user = user
        route_path = mocker.patch.object(
            db_request,
            "route_path",
            autospec=True,
            return_value=f"/project/{project.name}/",
        )

        result = views.submit_malware_observation(project, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == f"/project/{project.name}/"
        assert db_request.session.peek_flash("success") == [
            "Your report has been recorded. Thank you for your help."
        ]
        route_path.assert_called_once_with("packaging.project", name=project.name)
        assert len(project.observations) == 1


class TestEditProjectButton:
    def test_edit_project_button_returns_project(self, mocker):
        project = ProjectFactory.build()
        assert views.edit_project_button(project, mocker.sentinel.request) == {
            "project": project
        }
