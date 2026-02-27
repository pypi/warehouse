# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from natsort import natsorted
from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound

from warehouse.packaging import views

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

        db_request.matchdict = {"name": project.name.swapcase()}
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
    def test_normalizing_name_redirects(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="3.0")

        db_request.matchdict = {"name": project.name.swapcase()}
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
                (r.version, r.created, r.is_prerelease, r.yanked, r.yanked_reason)
                for r in reversed(releases)
            ],
            "maintainers": sorted(users, key=lambda u: u.username.lower()),
            "license": None,
            "PEP740AttestationViewer": views.PEP740AttestationViewer,
            "wheel_filters_all": {"interpreters": [], "abis": [], "platforms": []},
            "wheel_filters_params": {
                "filename": "",
                "interpreters": "",
                "abis": "",
                "platforms": "",
            },
        }

    def test_detail_renders_files_natural_sort(self, db_request):
        """Tests that when a release has multiple versions of Python,
        the sort order is most recent Python version first."""
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="3.0")
        files = [
            FileFactory.create(
                release=release,
                filename="-".join(
                    [project.name, release.version, py_ver, py_abi, py_platform]
                )
                + ".whl",
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
            {"interpreters": ["cp310"], "abis": ["none"], "platforms": ["any"]},
            {"interpreters": ["cp39"], "abis": ["none"], "platforms": ["any"]},
            {"interpreters": ["cp27"], "abis": ["none"], "platforms": ["any"]},
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
        github_publisher = pretend.stub(
            kind="GitHub",
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

        assert viewer.permalink_with_digest == (
            "https://github.com/pypa/sampleproject/tree/"
            "621e4974ca25ce531773def586ba3ed8e736b3fc"
        )
        assert (
            viewer.permalink_with_reference
            == "https://github.com/pypa/sampleproject/tree/refs/heads/main"
        )

    def test_gitlab_pep740(self, gitlab_attestation):
        gitlab_publisher = pretend.stub(
            kind="GitLab",
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
            publisher=pretend.stub(
                kind="Unknown",
            ),
            attestation=pretend.stub(certificate_claims={}),
        )

        assert viewer.workflow_filename == ""
        assert (
            viewer._format_url("https://example.com", "refs/heads/main")
            == "https://example.com/refs/heads/main"
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
