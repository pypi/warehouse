# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound

from warehouse.legacy.api import json
from warehouse.packaging.models import LifecycleStatus, ReleaseURL

from ....common.db.accounts import UserFactory
from ....common.db.integrations import VulnerabilityRecordFactory
from ....common.db.organizations import OrganizationProjectFactory
from ....common.db.packaging import (
    DescriptionFactory,
    FileFactory,
    JournalEntryFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
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


class TestLatestReleaseFactory:
    def test_missing_release(self, db_request):
        project = ProjectFactory.create()
        db_request.matchdict = {"name": project.normalized_name}
        resp = json.latest_release_factory(db_request)
        assert isinstance(resp, HTTPNotFound)
        _assert_has_cors_headers(resp.headers)

    def test_with_prereleases(self, monkeypatch, db_request):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0")
        ReleaseFactory.create(project=project, version="2.0")
        ReleaseFactory.create(project=project, version="4.0.dev0")

        release = ReleaseFactory.create(project=project, version="3.0")
        db_request.matchdict = {"name": project.normalized_name}
        assert json.latest_release_factory(db_request) == release

    def test_only_prereleases(self, monkeypatch, db_request):
        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0.dev0")
        ReleaseFactory.create(project=project, version="2.0.dev0")

        release = ReleaseFactory.create(project=project, version="3.0.dev0")
        db_request.matchdict = {"name": project.normalized_name}
        assert json.latest_release_factory(db_request) == release

    def test_all_releases_yanked(self, monkeypatch, db_request):
        """
        If all releases are yanked, the endpoint should return the same release as
        if none of the releases are yanked.
        """

        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0", yanked=True)
        ReleaseFactory.create(project=project, version="2.0", yanked=True)
        ReleaseFactory.create(project=project, version="4.0.dev0", yanked=True)

        release = ReleaseFactory.create(project=project, version="3.0", yanked=True)
        db_request.matchdict = {"name": project.normalized_name}
        assert json.latest_release_factory(db_request) == release

    def test_latest_release_yanked(self, monkeypatch, db_request):
        """
        If the latest version is yanked, the endpoint should fall back on the
        latest non-prerelease version that is not yanked, if one is available.
        """

        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0")
        ReleaseFactory.create(project=project, version="3.0", yanked=True)
        ReleaseFactory.create(project=project, version="3.0.dev0")

        release = ReleaseFactory.create(project=project, version="2.0")
        db_request.matchdict = {"name": project.normalized_name}
        assert json.latest_release_factory(db_request) == release

    def test_all_non_prereleases_yanked(self, monkeypatch, db_request):
        """
        If all non-prerelease versions are yanked, the endpoint should return the
        latest prerelease version that is not yanked.
        """

        project = ProjectFactory.create()

        ReleaseFactory.create(project=project, version="1.0", yanked=True)
        ReleaseFactory.create(project=project, version="2.0", yanked=True)
        ReleaseFactory.create(project=project, version="3.0", yanked=True)
        ReleaseFactory.create(project=project, version="3.0.dev0", yanked=True)

        release = ReleaseFactory.create(project=project, version="2.0.dev0")
        db_request.matchdict = {"name": project.normalized_name}
        assert json.latest_release_factory(db_request) == release

    def test_project_quarantined(self, monkeypatch, db_request):
        project = ProjectFactory.create(
            lifecycle_status=LifecycleStatus.QuarantineEnter
        )
        ReleaseFactory.create(project=project, version="1.0")

        db_request.matchdict = {"name": project.normalized_name}
        resp = json.latest_release_factory(db_request)

        assert isinstance(resp, HTTPNotFound)
        _assert_has_cors_headers(resp.headers)


class TestJSONProject:
    def test_normalizing_redirects(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")

        db_request.matchdict = {"name": project.name.swapcase()}
        db_request.current_route_path = pretend.call_recorder(
            lambda name: "/project/the-redirect/"
        )

        resp = json.json_project(release, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/"
        _assert_has_cors_headers(resp.headers)
        assert db_request.current_route_path.calls == [
            pretend.call(name=project.normalized_name)
        ]

    def test_renders(self, pyramid_config, db_request, db_session):
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
        for project_url in sorted(
            project_urls, key=lambda u: u.split(",", 1)[0].strip().lower()
        ):
            expected_urls.append(tuple(project_url.split(",", 1)))
        expected_urls = dict(tuple(expected_urls))

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
            label, _, purl = urlspec.partition(",")
            db_session.add(
                ReleaseURL(
                    release=releases[3],
                    name=label.strip(),
                    url=purl.strip(),
                )
            )

        files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.tar.gz",
                python_version="source",
                size=200,
            )
            for r in releases[1:]
        ]
        user = UserFactory.create()
        JournalEntryFactory.reset_sequence()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        db_request.route_url = pretend.call_recorder(lambda *args, **kw: url)
        db_request.matchdict = {"name": project.normalized_name}

        result = json.json_project(releases[-1], db_request)

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
                "dynamic": None,
                "home_page": None,
                "keywords": None,
                "license": None,
                "license_expression": None,
                "license_files": None,
                "maintainer": None,
                "maintainer_email": None,
                "name": project.name,
                "package_url": "/the/fake/url/",
                "platform": None,
                "project_url": "/the/fake/url/",
                "project_urls": expected_urls,
                "provides_extra": None,
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
                        "has_sig": False,
                        "md5_digest": files[0].md5_digest,
                        "digests": {
                            "md5": files[0].md5_digest,
                            "sha256": files[0].sha256_digest,
                            "blake2b_256": files[0].blake2_256_digest,
                        },
                        "packagetype": files[0].packagetype,
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
                        "has_sig": False,
                        "md5_digest": files[1].md5_digest,
                        "digests": {
                            "md5": files[1].md5_digest,
                            "sha256": files[1].sha256_digest,
                            "blake2b_256": files[1].blake2_256_digest,
                        },
                        "packagetype": files[1].packagetype,
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
                        "has_sig": False,
                        "md5_digest": files[2].md5_digest,
                        "digests": {
                            "blake2b_256": files[2].blake2_256_digest,
                            "md5": files[2].md5_digest,
                            "sha256": files[2].sha256_digest,
                        },
                        "packagetype": files[2].packagetype,
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
                    "has_sig": False,
                    "md5_digest": files[2].md5_digest,
                    "digests": {
                        "md5": files[2].md5_digest,
                        "sha256": files[2].sha256_digest,
                        "blake2b_256": files[2].blake2_256_digest,
                    },
                    "packagetype": files[2].packagetype,
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
            "vulnerabilities": [],
            "ownership": {
                "roles": [],
                "organization": None,
            },
        }


class TestJSONProjectSlash:
    def test_normalizing_redirects(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")

        db_request.matchdict = {"name": project.name.swapcase()}
        db_request.current_route_path = pretend.call_recorder(
            lambda name: "/project/the-redirect/"
        )

        resp = json.json_project_slash(release, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/"
        _assert_has_cors_headers(resp.headers)
        assert db_request.current_route_path.calls == [
            pretend.call(name=project.normalized_name)
        ]


class TestReleaseFactory:
    def test_missing_release(self, db_request):
        project = ProjectFactory.create()
        db_request.matchdict = {"name": project.normalized_name, "version": "3.0"}
        resp = json.release_factory(db_request)
        assert isinstance(resp, HTTPNotFound)
        _assert_has_cors_headers(resp.headers)

    def test_missing_release_with_multiple_canonical(self, db_request):
        project = ProjectFactory.create()
        ReleaseFactory.create(project=project, version="3.0.0")
        ReleaseFactory.create(project=project, version="3.0.0.0")
        db_request.matchdict = {"name": project.normalized_name, "version": "3.0"}
        resp = json.release_factory(db_request)
        assert isinstance(resp, HTTPNotFound)
        _assert_has_cors_headers(resp.headers)

    def test_project_quarantined(self, db_request):
        project = ProjectFactory.create(
            lifecycle_status=LifecycleStatus.QuarantineEnter
        )
        ReleaseFactory.create(project=project, version="1.0")

        db_request.matchdict = {"name": project.normalized_name, "version": "1.0"}
        resp = json.release_factory(db_request)

        assert isinstance(resp, HTTPNotFound)
        _assert_has_cors_headers(resp.headers)

    @pytest.mark.parametrize(
        ("other_versions", "the_version", "lookup_version"),
        [
            (["0.1", "1.0", "2.0"], "3.0", "3.0"),
            (["0.1", "1.0", "2.0"], "3.0.0", "3.0"),
            (["0.1", "1.0", "2.0", "3.0.0"], "3.0.0.0.0", "3.0.0.0.0"),
        ],
    )
    def test_lookup_release(
        self, db_request, other_versions, the_version, lookup_version
    ):
        project = ProjectFactory.create()
        releases = [
            ReleaseFactory.create(project=project, version=v) for v in other_versions
        ]
        releases += [ReleaseFactory.create(project=project, version=the_version)]

        user = UserFactory.create()
        JournalEntryFactory.reset_sequence()
        JournalEntryFactory.create(name=project.name, submitted_by=user)

        db_request.matchdict = {
            "name": project.normalized_name,
            "version": lookup_version,
        }

        assert json.release_factory(db_request) == releases[-1]


class TestJSONRelease:
    def test_normalizing_redirects(self, db_request):
        release = ReleaseFactory.create(version="3.0")

        db_request.matchdict = {
            "name": release.project.name.swapcase(),
            "version": "3.0",
        }
        db_request.current_route_path = pretend.call_recorder(
            lambda name: "/project/the-redirect/3.0/"
        )

        resp = json.json_release(release, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/3.0/"
        _assert_has_cors_headers(resp.headers)
        assert db_request.current_route_path.calls == [
            pretend.call(name=release.project.normalized_name)
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
        for project_url in sorted(
            project_urls, key=lambda u: u.split(",", 1)[0].strip().lower()
        ):
            expected_urls.append(tuple(project_url.split(",", 1)))
        expected_urls = dict(tuple(expected_urls))

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
                dynamic=["Platform", "Supported-Platform"],
                provides_extra=["testing", "plugin"],
            )
        ]

        for urlspec in project_urls:
            label, _, purl = urlspec.partition(",")
            db_session.add(
                ReleaseURL(
                    release=releases[-1],
                    name=label.strip(),
                    url=purl.strip(),
                )
            )

        files = [
            FileFactory.create(
                release=r,
                filename=f"{project.name}-{r.version}.tar.gz",
                python_version="source",
                size=200,
            )
            for r in releases[1:]
        ]
        user = UserFactory.create()
        JournalEntryFactory.reset_sequence()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        db_request.route_url = pretend.call_recorder(lambda *args, **kw: url)
        db_request.matchdict = {
            "name": project.normalized_name,
            "version": "3.0",
        }

        result = json.json_release(releases[-1], db_request)

        assert set(db_request.route_url.calls) == {
            pretend.call("packaging.file", path=files[-1].path),
            pretend.call("packaging.project", name=project.name),
            pretend.call(
                "packaging.release", name=project.name, version=releases[-1].version
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
                "dynamic": ["Platform", "Supported-Platform"],
                "home_page": None,
                "keywords": None,
                "license": None,
                "license_expression": None,
                "license_files": None,
                "maintainer": None,
                "maintainer_email": None,
                "name": project.name,
                "package_url": "/the/fake/url/",
                "platform": None,
                "project_url": "/the/fake/url/",
                "project_urls": expected_urls,
                "provides_extra": ["testing", "plugin"],
                "release_url": "/the/fake/url/",
                "requires_dist": None,
                "requires_python": None,
                "summary": None,
                "yanked": False,
                "yanked_reason": None,
                "version": "3.0",
            },
            "urls": [
                {
                    "comment_text": None,
                    "downloads": -1,
                    "filename": files[-1].filename,
                    "has_sig": False,
                    "md5_digest": files[-1].md5_digest,
                    "digests": {
                        "md5": files[-1].md5_digest,
                        "sha256": files[-1].sha256_digest,
                        "blake2b_256": files[-1].blake2_256_digest,
                    },
                    "packagetype": files[-1].packagetype,
                    "python_version": "source",
                    "size": 200,
                    "upload_time": files[-1].upload_time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "upload_time_iso_8601": files[-1].upload_time.isoformat() + "Z",
                    "url": "/the/fake/url/",
                    "requires_python": None,
                    "yanked": False,
                    "yanked_reason": None,
                }
            ],
            "last_serial": je.id,
            "vulnerabilities": [],
            "ownership": {
                "roles": [],
                "organization": None,
            },
        }

    def test_minimal_renders(self, pyramid_config, db_request):
        project = ProjectFactory.create(has_docs=False)
        release = ReleaseFactory.create(project=project, version="0.1")
        file = FileFactory.create(
            release=release,
            filename=f"{project.name}-{release.version}.tar.gz",
            python_version="source",
            size=200,
        )

        user = UserFactory.create()
        JournalEntryFactory.reset_sequence()
        je = JournalEntryFactory.create(name=project.name, submitted_by=user)

        url = "/the/fake/url/"
        db_request.route_url = pretend.call_recorder(lambda *args, **kw: url)
        db_request.matchdict = {
            "name": project.normalized_name,
            "version": release.canonical_version,
        }

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
                "dynamic": None,
                "home_page": None,
                "keywords": None,
                "license": None,
                "license_expression": None,
                "license_files": None,
                "maintainer": None,
                "maintainer_email": None,
                "name": project.name,
                "package_url": "/the/fake/url/",
                "platform": None,
                "project_url": "/the/fake/url/",
                "project_urls": None,
                "provides_extra": None,
                "release_url": "/the/fake/url/",
                "requires_dist": None,
                "requires_python": None,
                "summary": None,
                "yanked": False,
                "yanked_reason": None,
                "version": "0.1",
            },
            "urls": [
                {
                    "comment_text": None,
                    "downloads": -1,
                    "filename": file.filename,
                    "has_sig": False,
                    "md5_digest": file.md5_digest,
                    "digests": {
                        "md5": file.md5_digest,
                        "sha256": file.sha256_digest,
                        "blake2b_256": file.blake2_256_digest,
                    },
                    "packagetype": file.packagetype,
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
            "vulnerabilities": [],
            "ownership": {
                "roles": [],
                "organization": None,
            },
        }

    @pytest.mark.parametrize("withdrawn", [None, "2022-06-28T16:39:06Z"])
    def test_vulnerabilities_renders(self, pyramid_config, db_request, withdrawn):
        project = ProjectFactory.create(has_docs=False)
        release = ReleaseFactory.create(project=project, version="0.1")
        VulnerabilityRecordFactory.create(
            id="PYSEC-001",
            source="the source",
            link="the link",
            aliases=["alias1", "alias2"],
            details="some details",
            summary="some summary",
            fixed_in=["3.3.2"],
            releases=[release],
            withdrawn=withdrawn,
        )

        url = "/the/fake/url/"
        db_request.route_url = pretend.call_recorder(lambda *args, **kw: url)
        db_request.matchdict = {
            "name": project.normalized_name,
            "version": release.canonical_version,
        }

        result = json.json_release(release, db_request)

        assert result["vulnerabilities"] == [
            {
                "id": "PYSEC-001",
                "source": "the source",
                "link": "the link",
                "aliases": ["alias1", "alias2"],
                "details": "some details",
                "summary": "some summary",
                "fixed_in": ["3.3.2"],
                "withdrawn": withdrawn,
            },
        ]
        assert result["ownership"] == {"roles": [], "organization": None}

    def test_ownership_with_organization(self, pyramid_config, db_request):
        release = ReleaseFactory.create()
        project = release.project

        org_project = OrganizationProjectFactory.create(project=project)

        # Create roles out of insertion order to verify sorting:
        # Owners before Maintainers, then alphabetical within each role.
        RoleFactory.create(
            role_name="Maintainer",
            user=UserFactory.create(username="charlie"),
            project=project,
        )
        RoleFactory.create(
            role_name="Owner",
            user=UserFactory.create(username="bob"),
            project=project,
        )
        RoleFactory.create(
            role_name="Owner",
            user=UserFactory.create(username="alice"),
            project=project,
        )
        RoleFactory.create(
            role_name="Maintainer",
            user=UserFactory.create(username="dave"),
            project=project,
        )

        db_request.route_url = pretend.call_recorder(lambda *args, **kw: "/url/")
        db_request.matchdict = {
            "name": project.normalized_name,
            "version": release.canonical_version,
        }

        result = json.json_release(release, db_request)

        assert result["ownership"] == {
            "roles": [
                {"role": "Owner", "user": "alice"},
                {"role": "Owner", "user": "bob"},
                {"role": "Maintainer", "user": "charlie"},
                {"role": "Maintainer", "user": "dave"},
            ],
            "organization": org_project.organization.name,
        }


class TestJSONReleaseSlash:
    def test_normalizing_redirects(self, db_request):
        release = ReleaseFactory.create(version="3.0")

        db_request.matchdict = {
            "name": release.project.name.swapcase(),
            "version": "3.0",
        }
        db_request.current_route_path = pretend.call_recorder(
            lambda name: "/project/the-redirect/3.0/"
        )

        resp = json.json_release_slash(release, db_request)

        assert isinstance(resp, HTTPMovedPermanently)
        assert resp.headers["Location"] == "/project/the-redirect/3.0/"
        _assert_has_cors_headers(resp.headers)
        assert db_request.current_route_path.calls == [
            pretend.call(name=release.project.normalized_name)
        ]


class TestJSONUser:
    def test_no_projects(self, db_request):
        user = UserFactory.create()
        resp = json.json_user(user, db_request)
        assert resp["projects"] == []

    def test_has_projects(self, db_request):
        user = UserFactory.create()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")

        user.projects.append(project)

        resp = json.json_user(user, db_request)
        assert resp["projects"][0] == {
            "name": project.name,
            "last_released": release.created.strftime("%Y-%m-%dT%H:%M:%S"),
            "summary": release.summary,
        }

    def test_has_name(self, db_request):
        user = UserFactory.create()
        resp = json.json_user(user, db_request)
        assert resp["name"] == user.name
        assert resp["username"] == user.username

    def test_has_no_name(self, db_request):
        user = UserFactory.create(name="")
        resp = json.json_user(user, db_request)
        assert resp["name"] is None
        assert resp["username"] == user.username

    def test_project_without_releases(self, db_request):
        user = UserFactory.create()
        project = ProjectFactory.create()
        user.projects.append(project)

        resp = json.json_user(user, db_request)
        assert resp["projects"] == []


class TestJSONUserSlash:
    def test_redirect(self, db_request):
        user = UserFactory.create()
        resp = json.json_user_slash(user, db_request)
        assert resp["username"] == user.username
