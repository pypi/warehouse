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

from pyramid.httpexceptions import HTTPMovedPermanently
from pyramid.testing import DummyRequest

from warehouse.api import simple

from ...common.db.accounts import UserFactory
from ...common.db.packaging import (
    FileFactory,
    JournalEntryFactory,
    ProjectFactory,
    ReleaseFactory,
)


class TestContentNegotiation:
    @pytest.mark.parametrize("header", [None, "text/plain"])
    def test_defaults_text_html(self, header):
        """
        Ensures that, at least until we want to change the default, that we
        default to text/html.
        """
        request = DummyRequest(accept=header)
        assert simple._select_content_type(request) == "text/html"

    @pytest.mark.parametrize(
        "header, expected",
        [
            ("text/html", "text/html"),
            (
                "application/vnd.pypi.simple.v1+html",
                "application/vnd.pypi.simple.v1+html",
            ),
            (
                "application/vnd.pypi.simple.v1+json",
                "application/vnd.pypi.simple.v1+json",
            ),
            (
                "text/html, application/vnd.pypi.simple.v1+html, "
                "application/vnd.pypi.simple.v1+json",
                "text/html",
            ),
            (
                "text/html;q=0.01, application/vnd.pypi.simple.v1+html;q=0.2, "
                "application/vnd.pypi.simple.v1+json",
                "application/vnd.pypi.simple.v1+json",
            ),
        ],
    )
    def test_selects(self, header, expected):
        request = DummyRequest(accept=header)
        assert simple._select_content_type(request) == expected


CONTENT_TYPE_PARAMS = [
    ("text/html", None),
    ("application/vnd.pypi.simple.v1+html", None),
    ("application/vnd.pypi.simple.v1+json", "json"),
]


class TestSimpleIndex:
    @pytest.mark.parametrize(
        "content_type,renderer_override",
        CONTENT_TYPE_PARAMS,
    )
    def test_no_results_no_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        assert simple.simple_index(db_request) == {
            "meta": {"_last-serial": 0, "api-version": "1.0"},
            "projects": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"
        assert db_request.response.content_type == content_type

        if renderer_override is not None:
            db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        "content_type,renderer_override",
        CONTENT_TYPE_PARAMS,
    )
    def test_no_results_with_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        user = UserFactory.create()
        je = JournalEntryFactory.create(submitted_by=user)
        assert simple.simple_index(db_request) == {
            "meta": {"_last-serial": je.id, "api-version": "1.0"},
            "projects": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
        assert db_request.response.content_type == content_type

        if renderer_override is not None:
            db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        "content_type,renderer_override",
        CONTENT_TYPE_PARAMS,
    )
    def test_with_results_no_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        projects = [
            (x.name, x.normalized_name)
            for x in [ProjectFactory.create() for _ in range(3)]
        ]
        assert simple.simple_index(db_request) == {
            "meta": {"_last-serial": 0, "api-version": "1.0"},
            "projects": [{"name": x[0]} for x in sorted(projects, key=lambda x: x[1])],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"
        assert db_request.response.content_type == content_type

        if renderer_override is not None:
            db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        "content_type,renderer_override",
        CONTENT_TYPE_PARAMS,
    )
    def test_with_results_with_serial(
        self, db_request, content_type, renderer_override
    ):
        db_request.accept = content_type
        projects = [
            (x.name, x.normalized_name)
            for x in [ProjectFactory.create() for _ in range(3)]
        ]
        user = UserFactory.create()
        je = JournalEntryFactory.create(submitted_by=user)

        assert simple.simple_index(db_request) == {
            "meta": {"_last-serial": je.id, "api-version": "1.0"},
            "projects": [{"name": x[0]} for x in sorted(projects, key=lambda x: x[1])],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
        assert db_request.response.content_type == content_type

        if renderer_override is not None:
            db_request.override_renderer == renderer_override


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
        assert pyramid_request.current_route_path.calls == [pretend.call(name="foo")]

    @pytest.mark.parametrize(
        "content_type,renderer_override",
        CONTENT_TYPE_PARAMS,
    )
    def test_no_files_no_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        project = ProjectFactory.create()
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        JournalEntryFactory.create(submitted_by=user)

        assert simple.simple_detail(project, db_request) == {
            "meta": {"_last-serial": 0, "api-version": "1.0"},
            "name": project.normalized_name,
            "files": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"
        assert db_request.response.content_type == content_type

        if renderer_override is not None:
            db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        "content_type,renderer_override",
        CONTENT_TYPE_PARAMS,
    )
    def test_no_files_with_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        project = ProjectFactory.create()
        db_request.matchdict["name"] = project.normalized_name
        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        assert simple.simple_detail(project, db_request) == {
            "meta": {"_last-serial": je.id, "api-version": "1.0"},
            "name": project.normalized_name,
            "files": [],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
        assert db_request.response.content_type == content_type

        if renderer_override is not None:
            db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        "content_type,renderer_override",
        CONTENT_TYPE_PARAMS,
    )
    def test_with_files_no_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        project = ProjectFactory.create()
        releases = [ReleaseFactory.create(project=project) for _ in range(3)]
        files = [
            FileFactory.create(
                release=r, filename="{}-{}.tar.gz".format(project.name, r.version)
            )
            for r in releases
        ]
        # let's assert the result is ordered by string comparison of filename
        files = sorted(files, key=lambda key: key.filename)
        urls_iter = (f"/file/{f.filename}" for f in files)
        db_request.matchdict["name"] = project.normalized_name
        db_request.route_url = lambda *a, **kw: next(urls_iter)
        user = UserFactory.create()
        JournalEntryFactory.create(submitted_by=user)

        assert simple.simple_detail(project, db_request) == {
            "meta": {"_last-serial": 0, "api-version": "1.0"},
            "name": project.normalized_name,
            "files": [
                {
                    "filename": f.filename,
                    "url": f"/file/{f.filename}",
                    "hashes": {"sha256": f.sha256_digest},
                    "requires-python": f.requires_python,
                    "yanked": False,
                }
                for f in files
            ],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == "0"
        assert db_request.response.content_type == content_type

        if renderer_override is not None:
            db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        "content_type,renderer_override",
        CONTENT_TYPE_PARAMS,
    )
    def test_with_files_with_serial(self, db_request, content_type, renderer_override):
        db_request.accept = content_type
        project = ProjectFactory.create()
        releases = [ReleaseFactory.create(project=project) for _ in range(3)]
        files = [
            FileFactory.create(
                release=r, filename="{}-{}.tar.gz".format(project.name, r.version)
            )
            for r in releases
        ]
        # let's assert the result is ordered by string comparison of filename
        files = sorted(files, key=lambda key: key.filename)
        urls_iter = (f"/file/{f.filename}" for f in files)
        db_request.matchdict["name"] = project.normalized_name
        db_request.route_url = lambda *a, **kw: next(urls_iter)
        user = UserFactory.create()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        assert simple.simple_detail(project, db_request) == {
            "meta": {"_last-serial": je.id, "api-version": "1.0"},
            "name": project.normalized_name,
            "files": [
                {
                    "filename": f.filename,
                    "url": f"/file/{f.filename}",
                    "hashes": {"sha256": f.sha256_digest},
                    "requires-python": f.requires_python,
                    "yanked": False,
                }
                for f in files
            ],
        }
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
        assert db_request.response.content_type == content_type

        if renderer_override is not None:
            db_request.override_renderer == renderer_override

    @pytest.mark.parametrize(
        "content_type,renderer_override",
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
                filename="{}-{}.tar.gz".format(project.name, r.version),
                packagetype="sdist",
            )
            for r in releases
        ]
        wheel_files = [
            FileFactory.create(
                release=r,
                filename="{}-{}.whl".format(project.name, r.version),
                packagetype="bdist_wheel",
            )
            for r in releases
        ]
        egg_files = [
            FileFactory.create(
                release=r,
                filename="{}-{}.egg".format(project.name, r.version),
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

        assert simple.simple_detail(project, db_request) == {
            "meta": {"_last-serial": je.id, "api-version": "1.0"},
            "name": project.normalized_name,
            "files": [
                {
                    "filename": f.filename,
                    "url": f"/file/{f.filename}",
                    "hashes": {"sha256": f.sha256_digest},
                    "requires-python": f.requires_python,
                    "yanked": False,
                }
                for f in files
            ],
        }

        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)
        assert db_request.response.content_type == content_type

        if renderer_override is not None:
            db_request.override_renderer == renderer_override
