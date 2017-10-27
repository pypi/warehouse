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

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound

from warehouse.legacy.api import json

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    ProjectFactory, ReleaseFactory, FileFactory, JournalEntryFactory,
)


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
        assert db_request.current_route_path.calls == [
            pretend.call(name=project.name),
        ]

    def test_missing_release(self, db_request):
        project = ProjectFactory.create()
        resp = json.json_project(project, db_request)
        assert isinstance(resp, HTTPNotFound)

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
        assert db_request.current_route_path.calls == [
            pretend.call(name=release.project.name),
        ]

    def test_detail_renders(self, pyramid_config, db_request):
        project = ProjectFactory.create(has_docs=True)
        releases = [
            ReleaseFactory.create(project=project, version=v)
            for v in ["1.0", "2.0", "3.0"]
        ]
        files = [
            FileFactory.create(
                release=r,
                filename="{}-{}.tar.gz".format(project.name, r.version),
                python_version="source",
                size=200,
                has_signature=True,
            )
            for r in releases[:-1]
        ]
        user = UserFactory.create()
        JournalEntryFactory.reset_sequence()
        je = JournalEntryFactory.create(
            name=project.name,
            submitted_by=user,
        )

        daily_stats = pretend.stub()
        weekly_stats = pretend.stub()
        monthly_stats = pretend.stub()

        db_request.find_service = lambda x: pretend.stub(
            get_daily_stats=lambda p: daily_stats,
            get_weekly_stats=lambda p: weekly_stats,
            get_monthly_stats=lambda p: monthly_stats,
        )

        url = "/the/fake/url/"
        db_request.route_url = pretend.call_recorder(lambda *args, **kw: url)

        result = json.json_release(releases[1], db_request)

        assert set(db_request.route_url.calls) == {
            pretend.call("packaging.file", path=files[0].path),
            pretend.call("packaging.file", path=files[1].path),
            pretend.call("packaging.project", name=project.name),
            pretend.call(
                "packaging.release",
                name=project.name,
                version=releases[1].version,
            ),
            pretend.call("legacy.docs", project=project.name),
        }

        headers = db_request.response.headers
        assert headers["Access-Control-Allow-Origin"] == "*"
        assert headers["Access-Control-Allow-Headers"] == (
            "Content-Type, If-Match, If-Modified-Since, If-None-Match, "
            "If-Unmodified-Since"
        )
        assert headers["Access-Control-Allow-Methods"] == "GET"
        assert headers["Access-Control-Max-Age"] == "86400"
        assert headers["Access-Control-Expose-Headers"] == "X-PyPI-Last-Serial"
        assert headers["X-PyPI-Last-Serial"] == str(je.id)

        assert result == {
            "info": {
                "author": None,
                "author_email": None,
                "bugtrack_url": None,
                "classifiers": [],
                "description": None,
                "docs_url": "/the/fake/url/",
                "download_url": None,
                "downloads": {
                    "last_day": daily_stats,
                    "last_week": weekly_stats,
                    "last_month": monthly_stats,
                },
                "home_page": None,
                "keywords": None,
                "license": None,
                "maintainer": None,
                "maintainer_email": None,
                "name": project.name,
                "platform": None,
                "project_url": "/the/fake/url/",
                "release_url": "/the/fake/url/",
                "requires_dist": [],
                "requires_python": None,
                "summary": None,
                "version": "2.0",
            },
            "releases": {
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
                            "%Y-%m-%dT%H:%M:%S",
                        ),
                        "url": "/the/fake/url/",
                    },
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
                            "%Y-%m-%dT%H:%M:%S",
                        ),
                        "url": "/the/fake/url/",
                    },
                ],
                "3.0": [],
            },
            "urls": [
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
                        "%Y-%m-%dT%H:%M:%S",
                    ),
                    "url": "/the/fake/url/",
                },
            ],
        }
