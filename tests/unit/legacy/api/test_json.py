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

from collections import OrderedDict

import pretend

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound

from warehouse.legacy.api import json
from warehouse.packaging.models import Dependency, DependencyKind

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    DescriptionFactory,
    FileFactory,
    JournalEntryFactory,
    ProjectFactory,
    ReleaseFactory,
)


def _assert_has_cors_headers(headers):
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert headers["Access-Control-Allow-Headers"] == (
        "Content-Type, If-Match, If-Modified-Since, If-None-Match, "
        "If-Unmodified-Since"
    )
    assert headers["Access-Control-Allow-Methods"] == "GET"
    assert headers["Access-Control-Max-Age"] == "86400"
    assert headers["Access-Control-Expose-Headers"] == "X-PyPI-Last-Serial"


class TestJSONProject:
    def test_normalizing_redirects(self, db_request):
        project = ProjectFactory.create()

        name = project.name.lower()
        if name == project.name:
            name = project.name.upper()

        db_request.matchdict = {"name": name}
        db_request.current_route_path = pretend.call_recorder(
            lambda name: "/project/the-redirect/"
        )

        resp = json.json_project(project, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/"
        _assert_has_cors_headers(resp.headers)
        assert db_request.current_route_path.calls == [pretend.call(name=project.name)]

    def test_missing_release(self, db_request):
        project = ProjectFactory.create()
        resp = json.json_project(project, db_request)
        assert isinstance(resp, HTTPNotFound)
        _assert_has_cors_headers(resp.headers)

    def test_calls_release_detail(self, monkeypatch, db_request):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0")
        ReleaseFactory.create(project=project, version="2.0")

        release = ReleaseFactory.create(project=project, version="3.0")

        response = pretend.stub()
        json_release = pretend.call_recorder(lambda ctx, request: response)
        monkeypatch.setattr(json, "json_release", json_release)

        resp = json.json_project(project, db_request)

        assert resp is response
        assert json_release.calls == [pretend.call(release, db_request)]

    def test_with_prereleases(self, monkeypatch, db_request):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0")
        ReleaseFactory.create(project=project, version="2.0")
        ReleaseFactory.create(project=project, version="4.0.dev0")

        release = ReleaseFactory.create(project=project, version="3.0")

        response = pretend.stub()
        json_release = pretend.call_recorder(lambda ctx, request: response)
        monkeypatch.setattr(json, "json_release", json_release)

        resp = json.json_project(project, db_request)

        assert resp is response
        assert json_release.calls == [pretend.call(release, db_request)]

    def test_only_prereleases(self, monkeypatch, db_request):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0.dev0")
        ReleaseFactory.create(project=project, version="2.0.dev0")

        release = ReleaseFactory.create(project=project, version="3.0.dev0")

        response = pretend.stub()
        json_release = pretend.call_recorder(lambda ctx, request: response)
        monkeypatch.setattr(json, "json_release", json_release)

        resp = json.json_project(project, db_request)

        assert resp is response
        assert json_release.calls == [pretend.call(release, db_request)]


class TestJSONProjectSlash:
    def test_normalizing_redirects(self, db_request):
        project = ProjectFactory.create()

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/project/the-redirect"
        )

        resp = json.json_project_slash(project, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert db_request.route_path.calls == [
            pretend.call("legacy.api.json.project", name=project.name)
        ]
        assert resp.headers["Location"] == "/project/the-redirect"


class TestJSONRelease:
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

        resp = json.json_release(release, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/3.0/"
        _assert_has_cors_headers(resp.headers)
        assert db_request.current_route_path.calls == [
            pretend.call(name=release.project.name)
        ]

    def test_detail_renders(self, pyramid_config, db_request, db_session):
        project = ProjectFactory.create(has_docs=True)
        description_content_type = "text/x-rst"
        url = "/the/fake/url/"
        project_urls = [
            "url," + url,
            "Homepage,https://example.com/home2/",
            "Source Code,https://example.com/source-code/",
            "uri,http://john.doe@www.example.com:123/forum/questions/?tag=networking&order=newest#top",  # noqa: E501
            "ldap,ldap://[2001:db8::7]/c=GB?objectClass?one",
            "tel,tel:+1-816-555-1212",
            "telnet,telnet://192.0.2.16:80/",
            "urn,urn:oasis:names:specification:docbook:dtd:xml:4.1.2",
            "reservedchars,http://example.com?&$+/:;=@#",  # Commas don't work!
            r"unsafechars,http://example.com <>[]{}|\^%",
        ]
        expected_urls = []
        for project_url in reversed(project_urls):
            expected_urls.append(tuple(project_url.split(",")))
        expected_urls = OrderedDict(tuple(expected_urls))

        releases = [
            ReleaseFactory.create(project=project, version=v)
            for v in ["0.1", "1.0", "2.0"]
        ]
        releases += [
            ReleaseFactory.create(
                project=project,
                version="3.0",
                description=DescriptionFactory.create(
                    content_type=description_content_type
                ),
            )
        ]

        for urlspec in project_urls:
            db_session.add(
                Dependency(
                    release=releases[3],
                    kind=DependencyKind.project_url.value,
                    specifier=urlspec,
                )
            )

        files = [
            FileFactory.create(
                release=r,
                filename="{}-{}.tar.gz".format(project.name, r.version),
                python_version="source",
                size=200,
                has_signature=True,
            )
            for r in releases[1:]
        ]
        user = UserFactory.create()
        JournalEntryFactory.reset_sequence()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        db_request.route_url = pretend.call_recorder(lambda *args, **kw: url)

        result = json.json_release(releases[3], db_request)

        assert set(db_request.route_url.calls) == {
            pretend.call("packaging.file", path=files[0].path),
            pretend.call("packaging.file", path=files[1].path),
            pretend.call("packaging.file", path=files[2].path),
            pretend.call("packaging.project", name=project.name),
            pretend.call(
                "packaging.release", name=project.name, version=releases[3].version
            ),
            pretend.call("legacy.docs", project=project.name),
        }

        _assert_has_cors_headers(db_request.response.headers)
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)

        assert result == {
            "info": {
                "author": None,
                "author_email": None,
                "bugtrack_url": None,
                "classifiers": [],
                "description_content_type": description_content_type,
                "description": releases[-1].description.raw,
                "docs_url": "/the/fake/url/",
                "download_url": None,
                "downloads": {"last_day": -1, "last_week": -1, "last_month": -1},
                "home_page": None,
                "keywords": None,
                "license": None,
                "maintainer": None,
                "maintainer_email": None,
                "name": project.name,
                "package_url": "/the/fake/url/",
                "platform": None,
                "project_url": "/the/fake/url/",
                "project_urls": expected_urls,
                "release_url": "/the/fake/url/",
                "requires_dist": None,
                "requires_python": None,
                "summary": None,
                "yanked": False,
                "yanked_reason": None,
                "version": "3.0",
            },
            "releases": {
                "0.1": [],
                "1.0": [
                    {
                        "comment_text": None,
                        "downloads": -1,
                        "filename": files[0].filename,
                        "has_sig": True,
                        "md5_digest": files[0].md5_digest,
                        "digests": {
                            "md5": files[0].md5_digest,
                            "sha256": files[0].sha256_digest,
                        },
                        "packagetype": None,
                        "python_version": "source",
                        "size": 200,
                        "upload_time": files[0].upload_time.strftime(
                            "%Y-%m-%dT%H:%M:%S"
                        ),
                        "upload_time_iso_8601": files[0].upload_time.isoformat() + "Z",
                        "url": "/the/fake/url/",
                        "requires_python": None,
                        "yanked": False,
                        "yanked_reason": None,
                    }
                ],
                "2.0": [
                    {
                        "comment_text": None,
                        "downloads": -1,
                        "filename": files[1].filename,
                        "has_sig": True,
                        "md5_digest": files[1].md5_digest,
                        "digests": {
                            "md5": files[1].md5_digest,
                            "sha256": files[1].sha256_digest,
                        },
                        "packagetype": None,
                        "python_version": "source",
                        "size": 200,
                        "upload_time": files[1].upload_time.strftime(
                            "%Y-%m-%dT%H:%M:%S"
                        ),
                        "upload_time_iso_8601": files[1].upload_time.isoformat() + "Z",
                        "url": "/the/fake/url/",
                        "requires_python": None,
                        "yanked": False,
                        "yanked_reason": None,
                    }
                ],
                "3.0": [
                    {
                        "comment_text": None,
                        "downloads": -1,
                        "filename": files[2].filename,
                        "has_sig": True,
                        "md5_digest": files[2].md5_digest,
                        "digests": {
                            "md5": files[2].md5_digest,
                            "sha256": files[2].sha256_digest,
                        },
                        "packagetype": None,
                        "python_version": "source",
                        "size": 200,
                        "upload_time": files[2].upload_time.strftime(
                            "%Y-%m-%dT%H:%M:%S"
                        ),
                        "upload_time_iso_8601": files[2].upload_time.isoformat() + "Z",
                        "url": "/the/fake/url/",
                        "requires_python": None,
                        "yanked": False,
                        "yanked_reason": None,
                    }
                ],
            },
            "urls": [
                {
                    "comment_text": None,
                    "downloads": -1,
                    "filename": files[2].filename,
                    "has_sig": True,
                    "md5_digest": files[2].md5_digest,
                    "digests": {
                        "md5": files[2].md5_digest,
                        "sha256": files[2].sha256_digest,
                    },
                    "packagetype": None,
                    "python_version": "source",
                    "size": 200,
                    "upload_time": files[2].upload_time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "upload_time_iso_8601": files[2].upload_time.isoformat() + "Z",
                    "url": "/the/fake/url/",
                    "requires_python": None,
                    "yanked": False,
                    "yanked_reason": None,
                }
            ],
            "last_serial": je.id,
        }

    def test_minimal_renders(self, pyramid_config, db_request):
        project = ProjectFactory.create(has_docs=False)
        release = ReleaseFactory.create(project=project, version="0.1")
        file = FileFactory.create(
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
            size=200,
            has_signature=True,
        )

        user = UserFactory.create()
        JournalEntryFactory.reset_sequence()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        url = "/the/fake/url/"
        db_request.route_url = pretend.call_recorder(lambda *args, **kw: url)

        result = json.json_release(release, db_request)

        assert set(db_request.route_url.calls) == {
            pretend.call("packaging.file", path=file.path),
            pretend.call("packaging.project", name=project.name),
            pretend.call(
                "packaging.release", name=project.name, version=release.version
            ),
        }

        _assert_has_cors_headers(db_request.response.headers)
        assert db_request.response.headers["X-PyPI-Last-Serial"] == str(je.id)

        assert result == {
            "info": {
                "author": None,
                "author_email": None,
                "bugtrack_url": None,
                "classifiers": [],
                "description_content_type": release.description.content_type,
                "description": release.description.raw,
                "docs_url": None,
                "download_url": None,
                "downloads": {"last_day": -1, "last_week": -1, "last_month": -1},
                "home_page": None,
                "keywords": None,
                "license": None,
                "maintainer": None,
                "maintainer_email": None,
                "name": project.name,
                "package_url": "/the/fake/url/",
                "platform": None,
                "project_url": "/the/fake/url/",
                "project_urls": None,
                "release_url": "/the/fake/url/",
                "requires_dist": None,
                "requires_python": None,
                "summary": None,
                "yanked": False,
                "yanked_reason": None,
                "version": "0.1",
            },
            "releases": {
                "0.1": [
                    {
                        "comment_text": None,
                        "downloads": -1,
                        "filename": file.filename,
                        "has_sig": True,
                        "md5_digest": file.md5_digest,
                        "digests": {
                            "md5": file.md5_digest,
                            "sha256": file.sha256_digest,
                        },
                        "packagetype": None,
                        "python_version": "source",
                        "size": 200,
                        "upload_time": file.upload_time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "upload_time_iso_8601": file.upload_time.isoformat() + "Z",
                        "url": "/the/fake/url/",
                        "requires_python": None,
                        "yanked": False,
                        "yanked_reason": None,
                    }
                ]
            },
            "urls": [
                {
                    "comment_text": None,
                    "downloads": -1,
                    "filename": file.filename,
                    "has_sig": True,
                    "md5_digest": file.md5_digest,
                    "digests": {"md5": file.md5_digest, "sha256": file.sha256_digest},
                    "packagetype": None,
                    "python_version": "source",
                    "size": 200,
                    "upload_time": file.upload_time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "upload_time_iso_8601": file.upload_time.isoformat() + "Z",
                    "url": "/the/fake/url/",
                    "requires_python": None,
                    "yanked": False,
                    "yanked_reason": None,
                }
            ],
            "last_serial": je.id,
        }


class TestJSONReleaseSlash:
    def test_normalizing_redirects(self, db_request):
        release = ReleaseFactory.create()

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/project/the-redirect"
        )

        resp = json.json_release_slash(release, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert db_request.route_path.calls == [
            pretend.call(
                "legacy.api.json.release",
                name=release.project.name,
                version=release.version,
            )
        ]
        assert resp.headers["Location"] == "/project/the-redirect"
