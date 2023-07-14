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

import datetime

import pretend
import pytest

from warehouse.legacy.api.xmlrpc import views as xmlrpc
from warehouse.packaging.models import Classifier
from warehouse.rate_limiting.interfaces import IRateLimiter

from .....common.db.accounts import UserFactory
from .....common.db.packaging import (
    FileFactory,
    JournalEntryFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
)


class TestRateLimiting:
    def test_ratelimiting_pass(self, pyramid_services, pyramid_request, metrics):
        def view(context, request):
            return None

        ratelimited_view = xmlrpc.ratelimit()(view)
        context = pretend.stub()
        pyramid_request.remote_addr = "127.0.0.1"
        fake_rate_limiter = pretend.stub(
            test=lambda *a: True, hit=lambda *a: True, resets_in=lambda *a: None
        )
        pyramid_services.register_service(
            fake_rate_limiter, IRateLimiter, None, name="xmlrpc.client"
        )
        ratelimited_view(context, pyramid_request)

        assert metrics.increment.calls == [
            pretend.call("warehouse.xmlrpc.ratelimiter.hit", tags=[])
        ]

    def test_ratelimiting_block(self, pyramid_services, pyramid_request, metrics):
        def view(context, request):
            return None

        ratelimited_view = xmlrpc.ratelimit()(view)
        context = pretend.stub()
        pyramid_request.remote_addr = "127.0.0.1"
        fake_rate_limiter = pretend.stub(
            test=lambda *a: False, hit=lambda *a: True, resets_in=lambda *a: None
        )
        pyramid_services.register_service(
            fake_rate_limiter, IRateLimiter, None, name="xmlrpc.client"
        )
        with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
            ratelimited_view(context, pyramid_request)

        assert exc.value.faultString == (
            "HTTPTooManyRequests: The action could not be performed because there "
            "were too many requests by the client."
        )

        assert metrics.increment.calls == [
            pretend.call("warehouse.xmlrpc.ratelimiter.exceeded", tags=[])
        ]

    @pytest.mark.parametrize(
        "resets_in_delta, expected",
        [
            (datetime.timedelta(minutes=11, seconds=6.9), 666),
            (datetime.timedelta(seconds=0), 1),
        ],
    )
    def test_ratelimiting_block_with_hint(
        self, pyramid_services, pyramid_request, metrics, resets_in_delta, expected
    ):
        def view(context, request):
            return None

        ratelimited_view = xmlrpc.ratelimit()(view)
        context = pretend.stub()
        pyramid_request.remote_addr = "127.0.0.1"
        fake_rate_limiter = pretend.stub(
            test=lambda *a: False,
            hit=lambda *a: True,
            resets_in=lambda *a: resets_in_delta,
        )
        pyramid_services.register_service(
            fake_rate_limiter, IRateLimiter, None, name="xmlrpc.client"
        )
        with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
            ratelimited_view(context, pyramid_request)

        assert exc.value.faultString == (
            "HTTPTooManyRequests: The action could not be performed because there "
            "were too many requests by the client. Limit may reset in "
            f"{expected} seconds."
        )

        assert metrics.increment.calls == [
            pretend.call("warehouse.xmlrpc.ratelimiter.exceeded", tags=[])
        ]


class TestSearch:
    @pytest.mark.parametrize("domain", [None, "example.com"])
    def test_error(self, pyramid_request, metrics, monkeypatch, domain):
        registry_settings = {}
        if domain:
            registry_settings["warehouse.domain"] = domain
        monkeypatch.setattr(pyramid_request.registry, "settings", registry_settings)
        monkeypatch.setattr(pyramid_request, "domain", "example.org")

        with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
            xmlrpc.search(pyramid_request, {"name": "foo", "summary": ["one", "two"]})

        assert exc.value.faultString == (
            "RuntimeError: PyPI no longer supports 'pip search' (or XML-RPC search). "
            f"Please use https://{domain if domain else 'example.org'}/search "
            "(via a browser) instead. See "
            "https://warehouse.pypa.io/api-reference/xml-rpc.html#deprecated-methods "
            "for more information."
        )
        assert metrics.increment.calls == []


def test_list_packages(db_request):
    projects = ProjectFactory.create_batch(10)
    assert set(xmlrpc.list_packages(db_request)) == {p.name for p in projects}


def test_list_packages_with_serial(db_request):
    projects = ProjectFactory.create_batch(10)
    expected = {}
    for project in projects:
        expected.setdefault(project.name, 0)
        entries = JournalEntryFactory.create_batch(10, name=project.name)
        for entry in entries:
            if entry.id > expected[project.name]:
                expected[project.name] = entry.id
    assert xmlrpc.list_packages_with_serial(db_request) == expected


def test_package_hosting_mode_shows_none(db_request):
    assert xmlrpc.package_hosting_mode(db_request, "nope") == "pypi-only"


def test_package_hosting_mode_results(db_request):
    project = ProjectFactory.create()
    assert xmlrpc.package_hosting_mode(db_request, project.name) == "pypi-only"


def test_user_packages(db_request):
    user = UserFactory.create()
    other_user = UserFactory.create()
    owned_projects = ProjectFactory.create_batch(5)
    maintained_projects = ProjectFactory.create_batch(5)
    unowned_projects = ProjectFactory.create_batch(5)
    for project in owned_projects:
        RoleFactory.create(project=project, user=user)
    for project in maintained_projects:
        RoleFactory.create(project=project, user=user, role_name="Maintainer")
    for project in unowned_projects:
        RoleFactory.create(project=project, user=other_user)

    assert set(xmlrpc.user_packages(db_request, user.username)) == set(
        [("Owner", p.name) for p in sorted(owned_projects, key=lambda x: x.name)]
        + [
            ("Maintainer", p.name)
            for p in sorted(maintained_projects, key=lambda x: x.name)
        ]
    )


@pytest.mark.parametrize("num", [None, 1, 5])
def test_top_packages(num, pyramid_request):
    with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
        xmlrpc.top_packages(pyramid_request, num)

    assert exc.value.faultString == (
        "RuntimeError: This API has been removed. Use BigQuery instead. "
        "See https://warehouse.pypa.io/api-reference/xml-rpc.html#deprecated-methods "
        "for more information."
    )


@pytest.mark.parametrize("domain", [None, "example.com"])
def test_package_urls(domain, db_request):
    db_request.registry.settings = {}
    if domain:
        db_request.registry.settings = {"warehouse.domain": domain}
    db_request.domain = "example.org"
    with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
        xmlrpc.package_urls(db_request, "foo", "1.0.0")

    assert exc.value.faultString == (
        "RuntimeError: This API has been deprecated. "
        "See https://warehouse.pypa.io/api-reference/xml-rpc.html#deprecated-methods "
        "for more information."
    )


@pytest.mark.parametrize("domain", [None, "example.com"])
def test_package_data(domain, db_request):
    db_request.registry.settings = {}
    if domain:
        db_request.registry.settings = {"warehouse.domain": domain}
    db_request.domain = "example.org"
    with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
        xmlrpc.package_data(db_request, "foo", "1.0.0")

    assert exc.value.faultString == (
        "RuntimeError: This API has been deprecated. "
        "See https://warehouse.pypa.io/api-reference/xml-rpc.html#deprecated-methods "
        "for more information."
    )


def test_package_releases(db_request):
    project1 = ProjectFactory.create()
    releases1 = ReleaseFactory.create_batch(10, project=project1)
    project2 = ProjectFactory.create()
    ReleaseFactory.create_batch(10, project=project2)
    result = xmlrpc.package_releases(db_request, project1.name, show_hidden=False)
    assert (
        result
        == [
            r.version
            for r in reversed(sorted(releases1, key=lambda x: x._pypi_ordering))
        ][:1]
    )


def test_package_releases_hidden(db_request):
    project1 = ProjectFactory.create()
    releases1 = ReleaseFactory.create_batch(10, project=project1)
    project2 = ProjectFactory.create()
    ReleaseFactory.create_batch(10, project=project2)
    result = xmlrpc.package_releases(db_request, project1.name, show_hidden=True)
    assert result == [
        r.version for r in reversed(sorted(releases1, key=lambda x: x._pypi_ordering))
    ]


def test_package_releases_no_project(db_request):
    result = xmlrpc.package_releases(db_request, "foo")
    assert result == []


def test_package_releases_no_releases(db_request):
    project = ProjectFactory.create()
    result = xmlrpc.package_releases(db_request, project.name)
    assert result == []


def test_release_data_no_project(db_request):
    assert xmlrpc.release_data(db_request, "foo", "1.0") == {}


def test_release_data_no_release(db_request):
    project = ProjectFactory.create()
    assert xmlrpc.release_data(db_request, project.name, "1.0") == {}


def test_release_data(db_request):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)

    urls = [pretend.stub(), pretend.stub()]
    urls_iter = iter(urls)
    db_request.route_url = pretend.call_recorder(lambda r, **kw: next(urls_iter))

    assert xmlrpc.release_data(db_request, project.name, release.version) == {
        "name": release.project.name,
        "version": release.version,
        "stable_version": None,
        "bugtrack_url": None,
        "package_url": urls[0],
        "release_url": urls[1],
        "docs_url": release.project.documentation_url,
        "home_page": release.home_page,
        "download_url": release.download_url,
        "project_url": list(release.project_urls),
        "author": release.author,
        "author_email": release.author_email,
        "maintainer": release.maintainer,
        "maintainer_email": release.maintainer_email,
        "summary": release.summary,
        "description": release.description.raw,
        "license": release.license,
        "keywords": release.keywords,
        "platform": release.platform,
        "classifiers": list(release.classifiers),
        "requires": list(release.requires),
        "requires_dist": list(release.requires_dist),
        "provides": list(release.provides),
        "provides_dist": list(release.provides_dist),
        "obsoletes": list(release.obsoletes),
        "obsoletes_dist": list(release.obsoletes_dist),
        "requires_python": release.requires_python,
        "requires_external": list(release.requires_external),
        "_pypi_ordering": release._pypi_ordering,
        "downloads": {"last_day": -1, "last_week": -1, "last_month": -1},
        "cheesecake_code_kwalitee_id": None,
        "cheesecake_documentation_id": None,
        "cheesecake_installability_id": None,
    }
    assert db_request.route_url.calls == [
        pretend.call("packaging.project", name=project.name),
        pretend.call("packaging.release", name=project.name, version=release.version),
    ]


def test_release_urls(db_request):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    file_ = FileFactory.create(
        release=release,
        filename=f"{project.name}-{release.version}.tar.gz",
        python_version="source",
    )

    urls = [pretend.stub()]
    urls_iter = iter(urls)
    db_request.route_url = pretend.call_recorder(lambda r, **kw: next(urls_iter))

    assert xmlrpc.release_urls(db_request, project.name, release.version) == [
        {
            "filename": file_.filename,
            "packagetype": file_.packagetype,
            "python_version": file_.python_version,
            "size": file_.size,
            "md5_digest": file_.md5_digest,
            "sha256_digest": file_.sha256_digest,
            "digests": {"md5": file_.md5_digest, "sha256": file_.sha256_digest},
            "has_sig": False,
            "upload_time": file_.upload_time.isoformat() + "Z",
            "upload_time_iso_8601": file_.upload_time.isoformat() + "Z",
            "comment_text": file_.comment_text,
            "downloads": -1,
            "path": file_.path,
            "url": urls[0],
        }
    ]
    assert db_request.route_url.calls == [
        pretend.call("packaging.file", path=file_.path)
    ]


def test_package_roles(db_request):
    project1, project2 = ProjectFactory.create_batch(2)
    owners1 = RoleFactory.create_batch(3, project=project1)
    RoleFactory.create_batch(3, project=project2)
    maintainers1 = RoleFactory.create_batch(3, project=project1, role_name="Maintainer")
    RoleFactory.create_batch(3, project=project2, role_name="Maintainer")
    result = xmlrpc.package_roles(db_request, project1.name)
    assert result == [
        (r.role_name, r.user.username)
        for r in (
            sorted(owners1, key=lambda x: x.user.username.lower())
            + sorted(maintainers1, key=lambda x: x.user.username.lower())
        )
    ]


def test_changelog_last_serial_none(db_request):
    assert xmlrpc.changelog_last_serial(db_request) is None


def test_changelog_last_serial(db_request):
    projects = ProjectFactory.create_batch(10)
    entries = []
    for project in projects:
        entries.extend(JournalEntryFactory.create_batch(10, name=project.name))

    expected = max(e.id for e in entries)

    assert xmlrpc.changelog_last_serial(db_request) == expected


def test_changelog_since_serial(db_request):
    projects = ProjectFactory.create_batch(10)
    entries = []
    for project in projects:
        entries.extend(JournalEntryFactory.create_batch(10, name=project.name))

    expected = [
        (
            e.name,
            e.version,
            int(e.submitted_date.replace(tzinfo=datetime.UTC).timestamp()),
            e.action,
            e.id,
        )
        for e in entries
    ][int(len(entries) / 2) :]

    serial = entries[int(len(entries) / 2) - 1].id

    assert xmlrpc.changelog_since_serial(db_request, serial) == expected


@pytest.mark.parametrize("with_ids", [True, False, None])
def test_changelog(db_request, with_ids):
    projects = ProjectFactory.create_batch(10)
    entries = []
    for project in projects:
        entries.extend(JournalEntryFactory.create_batch(10, name=project.name))

    entries = sorted(entries, key=lambda x: x.id)

    since = int(
        entries[int(len(entries) / 2)]
        .submitted_date.replace(tzinfo=datetime.UTC)
        .timestamp()
    )

    expected = [
        (
            e.name,
            e.version,
            int(e.submitted_date.replace(tzinfo=datetime.UTC).timestamp()),
            e.action,
            e.id,
        )
        for e in entries
        if (e.submitted_date.replace(tzinfo=datetime.UTC).timestamp() > since)
    ]

    if not with_ids:
        expected = [e[:-1] for e in expected]

    extra_args = []
    if with_ids is not None:
        extra_args.append(with_ids)

    assert xmlrpc.changelog(db_request, since, *extra_args) == expected


def test_browse(db_request):
    classifiers = [
        Classifier(classifier="Environment :: Other Environment"),
        Classifier(classifier="Development Status :: 5 - Production/Stable"),
        Classifier(classifier="Programming Language :: Python"),
    ]
    for classifier in classifiers:
        db_request.db.add(classifier)

    projects = ProjectFactory.create_batch(3)
    releases = []
    for project in projects:
        releases.extend(
            ReleaseFactory.create_batch(
                10, project=project, _classifiers=[classifiers[0]]
            )
        )

    releases = sorted(releases, key=lambda x: (x.project.name, x.version))

    expected_release = releases[0]
    expected_release._classifiers = classifiers

    assert set(xmlrpc.browse(db_request, ["Environment :: Other Environment"])) == {
        (r.project.name, r.version) for r in releases
    }
    assert set(
        xmlrpc.browse(
            db_request,
            [
                "Environment :: Other Environment",
                "Development Status :: 5 - Production/Stable",
            ],
        )
    ) == {(expected_release.project.name, expected_release.version)}
    assert set(
        xmlrpc.browse(
            db_request,
            [
                "Environment :: Other Environment",
                "Development Status :: 5 - Production/Stable",
                "Programming Language :: Python",
            ],
        )
    ) == {(expected_release.project.name, expected_release.version)}
    assert set(
        xmlrpc.browse(
            db_request,
            [
                "Development Status :: 5 - Production/Stable",
                "Programming Language :: Python",
            ],
        )
    ) == {(expected_release.project.name, expected_release.version)}


def test_multicall(pyramid_request):
    with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
        xmlrpc.multicall(pyramid_request, [])

    assert exc.value.faultString == (
        "ValueError: MultiCall requests have been deprecated, use individual "
        "requests instead."
    )


@pytest.mark.parametrize(
    "string, expected", [("Hello…", "Hello&#8230;"), ("Stripe\x1b", "Stripe")]
)
def test_clean_for_xml(string, expected):
    assert xmlrpc._clean_for_xml(string) == expected
