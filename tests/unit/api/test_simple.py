# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from packaging.version import parse
from pyramid.httpexceptions import HTTPMovedPermanently
from pyramid.testing import DummyRequest

from tests.common.db.oidc import GitHubPublisherFactory
from warehouse.api import simple
from warehouse.packaging.utils import API_VERSION, _valid_simple_detail_context

from ...common.db.accounts import UserFactory
from ...common.db.packaging import (
    AlternateRepositoryFactory,
    FileFactory,
    JournalEntryFactory,
    ProjectFactory,
    ProvenanceFactory,
    ReleaseFactory,
)


def _assert_has_cors_headers(headers):
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert headers["Access-Control-Allow-Headers"] == (
        "Content-Type, If-Match, If-Modified-Since, If-None-Match, If-Unmodified-Since"
    )
    assert headers["Access-Control-Allow-Methods"] == "GET"
    assert headers["Access-Control-Max-Age"] == "86400"
    assert headers["Access-Control-Expose-Headers"] == "X-PyPI-Last-Serial"


class TestContentNegotiation:
    @pytest.mark.parametrize("header", [None, "text/plain"])
    def test_defaults_text_html(self, header):
        """
        Ensures that, at least until we want to change the default, that we
        default to text/html.
        """
        request = DummyRequest(accept=header)
        assert simple._select_content_type(request) == simple.MIME_TEXT_HTML

    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            (simple.MIME_TEXT_HTML, simple.MIME_TEXT_HTML),
            (
                simple.MIME_PYPI_SIMPLE_V1_HTML,
                simple.MIME_PYPI_SIMPLE_V1_HTML,
            ),
            (
                simple.MIME_PYPI_SIMPLE_V1_JSON,
                simple.MIME_PYPI_SIMPLE_V1_JSON,
            ),
            (
                f"{simple.MIME_TEXT_HTML}, {simple.MIME_PYPI_SIMPLE_V1_HTML}, "
                f"{simple.MIME_PYPI_SIMPLE_V1_JSON}",
                simple.MIME_TEXT_HTML,
            ),
            (
                f"{simple.MIME_TEXT_HTML};q=0.01, "
                f"{simple.MIME_PYPI_SIMPLE_V1_HTML};q=0.2, "
                f"{simple.MIME_PYPI_SIMPLE_V1_JSON}",
                simple.MIME_PYPI_SIMPLE_V1_JSON,
            ),
        ],
    )
    def test_selects(self, header, expected):
        request = DummyRequest(accept=header)
        assert simple._select_content_type(request) == expected


CONTENT_TYPE_PARAMS = [
    (simple.MIME_TEXT_HTML, None),
    (simple.MIME_PYPI_SIMPLE_V1_HTML, None),
    (simple.MIME_PYPI_SIMPLE_V1_JSON, "json"),
]


class TestSimpleIndex:
    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_no_results_no_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        assert simple.simple_index(db_request) == {
            "meta": {"_last-serial": 0, "api-version": API_VERSION},
            "projects": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"
        assert db_request.response.content_type == content_type
        _assert_has_cors_headers(db_request.response.headers)

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_no_results_with_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        user = UserFactory.create()
        je = JournalEntryFactory.create(submitted_by=user)
        assert simple.simple_index(db_request) == {
            "meta": {"_last-serial": je.id, "api-version": API_VERSION},
            "projects": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
        assert db_request.response.content_type == content_type
        _assert_has_cors_headers(db_request.response.headers)

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_with_results_no_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        projects = [(x.name, x.normalized_name) for x in ProjectFactory.create_batch(3)]
        assert simple.simple_index(db_request) == {
            "meta": {"_last-serial": 0, "api-version": API_VERSION},
            "projects": [
                {"name": x[0], "_last-serial": 0}
                for x in sorted(projects, key=lambda x: x[1])
            ],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"
        assert db_request.response.content_type == content_type
        _assert_has_cors_headers(db_request.response.headers)

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_with_results_with_serial(
        self, db_request, content_type, renderer_override
    ):
        db_request.accept = content_type
        projects = [(x.name, x.normalized_name) for x in ProjectFactory.create_batch(3)]
        user = UserFactory.create()
        je = JournalEntryFactory.create(submitted_by=user)

        assert simple.simple_index(db_request) == {
            "meta": {"_last-serial": je.id, "api-version": API_VERSION},
            "projects": [
                {"name": x[0], "_last-serial": 0}
                for x in sorted(projects, key=lambda x: x[1])
            ],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
        assert db_request.response.content_type == content_type
        _assert_has_cors_headers(db_request.response.headers)

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    def test_quarantined_project_omitted_from_index(self, db_request):
        db_request.accept = "text/html"
        ProjectFactory.create(name="foo")
        ProjectFactory.create(name="bar", lifecycle_status="quarantine-enter")

        assert simple.simple_index(db_request) == {
            "meta": {"_last-serial": 0, "api-version": API_VERSION},
            "projects": [{"name": "foo", "_last-serial": 0}],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"
        assert db_request.response.content_type == "text/html"
        _assert_has_cors_headers(db_request.response.headers)


class TestSimpleDetail:
    def test_redirects(self, pyramid_request):
        project = pretend.stub(normalized_name="foo")

        pyramid_request.matchdict["name"] = "Foo"
        pyramid_request.current_route_path = pretend.call_recorder(
            lambda name: "/foobar/"
        )

        resp = simple.simple_detail(project, pyramid_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/foobar/"
        _assert_has_cors_headers(resp.headers)
        assert pyramid_request.current_route_path.calls == [pretend.call(name="foo")]

    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_no_files_no_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        project = ProjectFactory.create()
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        JournalEntryFactory.create(submitted_by=user)

        context = {
            "meta": {"_last-serial": 0, "api-version": API_VERSION},
            "name": project.normalized_name,
            "project-status": {"status": "active"},
            "files": [],
            "versions": [],
            "alternate-locations": [],
        }
        context = _update_context(context, content_type, renderer_override)
        assert simple.simple_detail(project, db_request) == context

        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"
        assert db_request.response.content_type == content_type
        _assert_has_cors_headers(db_request.response.headers)

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_no_files_with_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        project = ProjectFactory.create()
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)
        als = [
            AlternateRepositoryFactory.create(project=project),
            AlternateRepositoryFactory.create(project=project),
        ]

        context = {
            "meta": {"_last-serial": je.id, "api-version": API_VERSION},
            "name": project.normalized_name,
            "project-status": {"status": "active"},
            "files": [],
            "versions": [],
            "alternate-locations": sorted(al.url for al in als),
        }
        context = _update_context(context, content_type, renderer_override)
        assert simple.simple_detail(project, db_request) == context

        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
        assert db_request.response.content_type == content_type
        _assert_has_cors_headers(db_request.response.headers)

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_with_files_no_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        project = ProjectFactory.create()
        releases = ReleaseFactory.create_batch(3, project=project)
        release_versions = sorted([r.version for r in releases], key=parse)
        files = [
            FileFactory.create(release=r, filename=f"{project.name}-{r.version}.tar.gz")
            for r in releases
        ]
        # let's assert the result is ordered by string comparison of version, filename
        files = sorted(files, key=lambda f: (parse(f.release.version), f.filename))
        urls_iter = (f"/file/{f.filename}" for f in files)
        db_request.matchdict["name"] = project.normalized_name
        db_request.route_url = lambda *a, **kw: next(urls_iter)
        user = UserFactory.create()
        JournalEntryFactory.create(submitted_by=user)

        context = {
            "meta": {"_last-serial": 0, "api-version": API_VERSION},
            "name": project.normalized_name,
            "project-status": {"status": "active"},
            "versions": release_versions,
            "files": [
                {
                    "filename": f.filename,
                    "url": f"/file/{f.filename}",
                    "hashes": {"sha256": f.sha256_digest},
                    "requires-python": f.requires_python,
                    "yanked": False,
                    "size": f.size,
                    "upload-time": f.upload_time.isoformat() + "Z",
                    "data-dist-info-metadata": False,
                    "core-metadata": False,
                    "provenance": None,
                }
                for f in files
            ],
            "alternate-locations": [],
        }
        context = _update_context(context, content_type, renderer_override)
        assert simple.simple_detail(project, db_request) == context

        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"
        assert db_request.response.content_type == content_type
        _assert_has_cors_headers(db_request.response.headers)

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_with_files_with_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        project = ProjectFactory.create()
        releases = ReleaseFactory.create_batch(3, project=project)
        release_versions = sorted([r.version for r in releases], key=parse)
        files = [
            FileFactory.create(release=r, filename=f"{project.name}-{r.version}.tar.gz")
            for r in releases
        ]
        # let's assert the result is ordered by version and filename
        files = sorted(files, key=lambda f: (parse(f.release.version), f.filename))
        urls_iter = (f"/file/{f.filename}" for f in files)
        db_request.matchdict["name"] = project.normalized_name
        db_request.route_url = lambda *a, **kw: next(urls_iter)
        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        context = {
            "meta": {"_last-serial": je.id, "api-version": API_VERSION},
            "name": project.normalized_name,
            "project-status": {"status": "active"},
            "versions": release_versions,
            "files": [
                {
                    "filename": f.filename,
                    "url": f"/file/{f.filename}",
                    "hashes": {"sha256": f.sha256_digest},
                    "requires-python": f.requires_python,
                    "yanked": False,
                    "size": f.size,
                    "upload-time": f.upload_time.isoformat() + "Z",
                    "data-dist-info-metadata": False,
                    "core-metadata": False,
                    "provenance": None,
                }
                for f in files
            ],
            "alternate-locations": [],
        }
        context = _update_context(context, content_type, renderer_override)
        assert simple.simple_detail(project, db_request) == context

        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
        assert db_request.response.content_type == content_type
        _assert_has_cors_headers(db_request.response.headers)

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_with_files_with_version_multi_digit(
        self, db_request, content_type, renderer_override
    ):
        db_request.accept = content_type
        project = ProjectFactory.create()
        release_versions = [
            "0.3.0rc1",
            "0.3.0",
            "0.3.0-post0",
            "0.14.0",
            "4.2.0",
            "24.2.0",
        ]
        releases = [
            ReleaseFactory.create(project=project, version=version)
            for version in release_versions
        ]

        tar_files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.tar.gz",
                packagetype="sdist",
            )
            for r in releases
        ]
        wheel_files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.whl",
                packagetype="bdist_wheel",
                metadata_file_sha256_digest="deadbeefdeadbeefdeadbeefdeadbeef",
            )
            for r in releases
        ]
        egg_files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.egg",
                packagetype="bdist_egg",
            )
            for r in releases
        ]

        files = []
        for files_release in zip(egg_files, tar_files, wheel_files):
            files += files_release

        urls_iter = (f"/file/{f.filename}" for f in files)
        db_request.matchdict["name"] = project.normalized_name
        db_request.route_url = lambda *a, **kw: next(urls_iter)
        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        context = {
            "meta": {"_last-serial": je.id, "api-version": API_VERSION},
            "name": project.normalized_name,
            "project-status": {"status": "active"},
            "versions": release_versions,
            "files": [
                {
                    "filename": f.filename,
                    "url": f"/file/{f.filename}",
                    "hashes": {"sha256": f.sha256_digest},
                    "requires-python": f.requires_python,
                    "yanked": False,
                    "size": f.size,
                    "upload-time": f.upload_time.isoformat() + "Z",
                    "data-dist-info-metadata": (
                        {"sha256": "deadbeefdeadbeefdeadbeefdeadbeef"}
                        if f.metadata_file_sha256_digest is not None
                        else False
                    ),
                    "core-metadata": (
                        {"sha256": "deadbeefdeadbeefdeadbeefdeadbeef"}
                        if f.metadata_file_sha256_digest is not None
                        else False
                    ),
                    "provenance": None,
                }
                for f in files
            ],
            "alternate-locations": [],
        }
        context = _update_context(context, content_type, renderer_override)
        assert simple.simple_detail(project, db_request) == context

        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
        assert db_request.response.content_type == content_type
        _assert_has_cors_headers(db_request.response.headers)

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_with_files_quarantined_omitted_from_index(
        self, db_request, content_type, renderer_override
    ):
        db_request.accept = content_type
        project = ProjectFactory.create(lifecycle_status="quarantine-enter")
        releases = ReleaseFactory.create_batch(3, project=project)
        _ = [
            FileFactory.create(release=r, filename=f"{project.name}-{r.version}.tar.gz")
            for r in releases
        ]

        context = {
            "meta": {"_last-serial": 0, "api-version": API_VERSION},
            "name": project.normalized_name,
            "project-status": {"status": "quarantined"},
            "files": [],
            "versions": [],
            "alternate-locations": [],
        }
        context = _update_context(context, content_type, renderer_override)

        assert simple.simple_detail(project, db_request) == context

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        "archive_marker",
        (
            "archived",
            "archived-noindex",
        ),
    )
    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_with_archived_project(
        self, db_request, archive_marker, content_type, renderer_override
    ):
        db_request.accept = content_type
        project = ProjectFactory.create(lifecycle_status=archive_marker)
        _ = ReleaseFactory.create_batch(3, project=project)

        context = {
            "meta": {"_last-serial": 0, "api-version": API_VERSION},
            "name": project.normalized_name,
            "project-status": {"status": "archived"},
            "files": [],
            "versions": [],
            "alternate-locations": [],
        }
        context = _update_context(context, content_type, renderer_override)

        assert simple.simple_detail(project, db_request) == context

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_with_quarantine_exit_project(
        self, db_request, content_type, renderer_override
    ):
        db_request.accept = content_type
        project = ProjectFactory.create(lifecycle_status="quarantine-exit")
        _ = ReleaseFactory.create_batch(3, project=project)

        context = {
            "meta": {"_last-serial": 0, "api-version": API_VERSION},
            "name": project.normalized_name,
            "project-status": {"status": "active"},
            "files": [],
            "versions": [],
            "alternate-locations": [],
        }
        context = _update_context(context, content_type, renderer_override)

        assert simple.simple_detail(project, db_request) == context

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        ("content_type", "renderer_override"),
        CONTENT_TYPE_PARAMS,
    )
    def test_with_files_varying_provenance(
        self,
        db_request,
        integrity_service,
        dummy_attestation,
        content_type,
        renderer_override,
    ):
        db_request.accept = content_type
        db_request.oidc_publisher = GitHubPublisherFactory.create()

        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0.0")

        # wheel with provenance, sdist with no provenance
        wheel = FileFactory.create(
            release=release,
            filename=f"{project.name}-1.0.0.whl",
            packagetype="bdist_wheel",
            metadata_file_sha256_digest="deadbeefdeadbeefdeadbeefdeadbeef",
        )

        provenance = ProvenanceFactory.create(file=wheel)
        assert wheel.provenance == provenance

        sdist = FileFactory.create(
            release=release,
            filename=f"{project.name}-1.0.0.tar.gz",
            packagetype="sdist",
        )

        files = [sdist, wheel]

        db_request.matchdict["name"] = project.normalized_name

        def route_url(route, **kw):
            # Rendering the simple index calls route_url once for each file,
            # and zero or one times per file depending on whether the file
            # has provenance. We emulate this while testing by maintaining
            # a dictionary of expected URLs for each route, which are
            # pulled from as appropriate when a route_url call is made.
            route_urls = {
                "packaging.file": {f.path: f"/file/{f.filename}" for f in files},
                "integrity.provenance": {
                    (
                        wheel.release.project.normalized_name,
                        wheel.release.version,
                        wheel.filename,
                    ): (
                        f"/integrity/{wheel.release.project.normalized_name}/"
                        f"{wheel.release.version}/{wheel.filename}/provenance"
                    )
                },
            }

            match route:
                case "packaging.file":
                    return route_urls[route].get(kw.get("path"), "")
                case "integrity.provenance":
                    key = (
                        kw.get("project_name"),
                        kw.get("release"),
                        kw.get("filename"),
                    )
                    return route_urls[route].get(key, "")
                case _:
                    pytest.fail(f"unexpected route: {route}")

        db_request.route_url = route_url

        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        context = {
            "meta": {"_last-serial": je.id, "api-version": API_VERSION},
            "name": project.normalized_name,
            "project-status": {"status": "active"},
            "versions": ["1.0.0"],
            "files": [
                {
                    "filename": f.filename,
                    "url": f"/file/{f.filename}",
                    "hashes": {"sha256": f.sha256_digest},
                    "requires-python": f.requires_python,
                    "yanked": False,
                    "size": f.size,
                    "upload-time": f.upload_time.isoformat() + "Z",
                    "data-dist-info-metadata": (
                        {"sha256": "deadbeefdeadbeefdeadbeefdeadbeef"}
                        if f.metadata_file_sha256_digest is not None
                        else False
                    ),
                    "core-metadata": (
                        {"sha256": "deadbeefdeadbeefdeadbeefdeadbeef"}
                        if f.metadata_file_sha256_digest is not None
                        else False
                    ),
                    "provenance": (
                        (
                            f"/integrity/{f.release.project.normalized_name}/"
                            f"{f.release.version}/{f.filename}/provenance"
                        )
                        if f.provenance is not None
                        else None
                    ),
                }
                for f in files
            ],
            "alternate-locations": [],
        }
        context = _update_context(context, content_type, renderer_override)

        assert simple.simple_detail(project, db_request) == context

        if renderer_override is not None:
            assert db_request.override_renderer == renderer_override


def _update_context(context, content_type, renderer_override):
    if renderer_override != "json" or content_type in [
        simple.MIME_TEXT_HTML,
        simple.MIME_PYPI_SIMPLE_V1_HTML,
    ]:
        return _valid_simple_detail_context(context)
    return context
