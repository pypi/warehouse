# SPDX-License-Identifier: Apache-2.0

import datetime

import pretend
import pytest

from pyramid.httpexceptions import HTTPMethodNotAllowed
from pyramid_rpc.xmlrpc import XmlRpcApplicationError

from warehouse.legacy.api.xmlrpc import views as xmlrpc
from warehouse.packaging.models import Classifier
from warehouse.rate_limiting.interfaces import IRateLimiter

from .....common.db.accounts import UserFactory
from .....common.db.packaging import (
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
        ("resets_in_delta", "expected"),
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


def test_list_packages(pyramid_request):
    with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
        xmlrpc.list_packages(pyramid_request)

    assert exc.value.faultString == (
        "RuntimeError: PyPI no longer supports the XMLRPC list_packages method. "
        "Use Simple API instead. "
        "See https://warehouse.pypa.io/api-reference/xml-rpc.html#deprecated-methods "
        "for more information."
    )


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


def test_package_releases(pyramid_request):
    with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
        xmlrpc.package_releases(pyramid_request, "project")

    assert exc.value.faultString == (
        "RuntimeError: PyPI no longer supports the XMLRPC package_releases method. "
        "Use JSON or Simple API instead. "
        "See https://warehouse.pypa.io/api-reference/xml-rpc.html#deprecated-methods "
        "for more information."
    )


def test_release_data(pyramid_request):
    with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
        xmlrpc.release_data(pyramid_request, "project", "version")

    assert exc.value.faultString == (
        "RuntimeError: PyPI no longer supports the XMLRPC release_data method. "
        "Use JSON or Simple API instead. "
        "See https://warehouse.pypa.io/api-reference/xml-rpc.html#deprecated-methods "
        "for more information."
    )


def test_release_urls(pyramid_request):
    with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
        xmlrpc.release_urls(pyramid_request, "project", "version")

    assert exc.value.faultString == (
        "RuntimeError: PyPI no longer supports the XMLRPC release_urls method. "
        "Use JSON or Simple API instead. "
        "See https://warehouse.pypa.io/api-reference/xml-rpc.html#deprecated-methods "
        "for more information."
    )


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


def test_changelog(pyramid_request):
    with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
        xmlrpc.changelog(pyramid_request, 0)

    assert exc.value.faultString == (
        "ValueError: The changelog method has been deprecated, use "
        "changelog_since_serial instead."
    )


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
    ("string", "expected"), [("Hello…", "Hello&#8230;"), ("Stripe\x1b", "Stripe")]
)
def test_clean_for_xml(string, expected):
    assert xmlrpc._clean_for_xml(string) == expected


def test_http_method_not_allowed_does_not_bubble_up(pyramid_request):
    assert isinstance(
        xmlrpc.exception_view(HTTPMethodNotAllowed(), pyramid_request),
        XmlRpcApplicationError,
    )
