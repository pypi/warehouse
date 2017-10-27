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

from warehouse.legacy.api import xmlrpc
from warehouse.packaging.interfaces import IDownloadStatService
from warehouse.packaging.models import Classifier

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    ProjectFactory, ReleaseFactory, FileFactory, RoleFactory,
    JournalEntryFactory,
)


class TestSearch:

    def test_fails_with_invalid_operator(self):
        with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
            xmlrpc.search(pretend.stub(), {}, "lol nope")

        assert exc.value.faultString == \
            "ValueError: Invalid operator, must be one of 'and' or 'or'."

    def test_fails_if_spec_not_mapping(self):
        with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
            xmlrpc.search(pretend.stub(), "a string")

        assert exc.value.faultString == \
            "TypeError: Invalid spec, must be a mapping/dictionary."

    def test_default_search_operator(self):
        class FakeQuery:
            def __init__(self, type, must):
                self.type = type
                self.must = must

            def __getitem__(self, name):
                self.offset = name.start
                self.limit = name.stop
                self.step = name.step
                return self

            def execute(self):
                assert self.type == "bool"
                assert [q.to_dict() for q in self.must] == [
                    {"match": {"name": "foo"}},
                    {
                        "bool": {
                            "should": [
                                {"match": {"summary": "one"}},
                                {"match": {"summary": "two"}},
                            ],
                        },
                    },
                ]
                assert self.offset is None
                assert self.limit == 1000
                assert self.step is None
                return [
                    pretend.stub(
                        name="foo",
                        summary="my summary",
                        version=["1.0"],
                    ),
                    pretend.stub(
                        name="foo-bar",
                        summary="other summary",
                        version=["2.0", "1.0"],
                    ),
                ]

        request = pretend.stub(es=pretend.stub(query=FakeQuery))
        results = xmlrpc.search(
            request,
            {"name": "foo", "summary": ["one", "two"]},
        )
        assert results == [
            {"name": "foo", "summary": "my summary", "version": "1.0"},
            {"name": "foo-bar", "summary": "other summary", "version": "2.0"},
            {"name": "foo-bar", "summary": "other summary", "version": "1.0"},
        ]

    def test_searches_with_and(self):
        class FakeQuery:
            def __init__(self, type, must):
                self.type = type
                self.must = must

            def __getitem__(self, name):
                self.offset = name.start
                self.limit = name.stop
                self.step = name.step
                return self

            def execute(self):
                assert self.type == "bool"
                assert [q.to_dict() for q in self.must] == [
                    {"match": {"name": "foo"}},
                    {
                        "bool": {
                            "should": [
                                {"match": {"summary": "one"}},
                                {"match": {"summary": "two"}},
                            ],
                        },
                    },
                ]
                assert self.offset is None
                assert self.limit == 1000
                assert self.step is None
                return [
                    pretend.stub(
                        name="foo",
                        summary="my summary",
                        version=["1.0"],
                    ),
                    pretend.stub(
                        name="foo-bar",
                        summary="other summary",
                        version=["2.0", "1.0"],
                    ),
                ]

        request = pretend.stub(es=pretend.stub(query=FakeQuery))
        results = xmlrpc.search(
            request,
            {"name": "foo", "summary": ["one", "two"]},
            "and",
        )
        assert results == [
            {"name": "foo", "summary": "my summary", "version": "1.0"},
            {"name": "foo-bar", "summary": "other summary", "version": "2.0"},
            {"name": "foo-bar", "summary": "other summary", "version": "1.0"},
        ]

    def test_searches_with_or(self):
        class FakeQuery:
            def __init__(self, type, should):
                self.type = type
                self.should = should

            def __getitem__(self, name):
                self.offset = name.start
                self.limit = name.stop
                self.step = name.step
                return self

            def execute(self):
                assert self.type == "bool"
                assert [q.to_dict() for q in self.should] == [
                    {"match": {"name": "foo"}},
                    {
                        "bool": {
                            "should": [
                                {"match": {"summary": "one"}},
                                {"match": {"summary": "two"}},
                            ],
                        },
                    },
                ]
                assert self.offset is None
                assert self.limit == 1000
                assert self.step is None
                return [
                    pretend.stub(
                        name="foo",
                        summary="my summary",
                        version=["1.0"],
                    ),
                    pretend.stub(
                        name="foo-bar",
                        summary="other summary",
                        version=["2.0", "1.0"],
                    ),
                ]

        request = pretend.stub(es=pretend.stub(query=FakeQuery))
        results = xmlrpc.search(
            request,
            {"name": "foo", "summary": ["one", "two"]},
            "or",
        )
        assert results == [
            {"name": "foo", "summary": "my summary", "version": "1.0"},
            {"name": "foo-bar", "summary": "other summary", "version": "2.0"},
            {"name": "foo-bar", "summary": "other summary", "version": "1.0"},
        ]


def test_list_packages(db_request):
    projects = [ProjectFactory.create() for _ in range(10)]
    assert set(xmlrpc.list_packages(db_request)) == {p.name for p in projects}


def test_list_packages_with_serial(db_request):
    projects = [ProjectFactory.create() for _ in range(10)]
    expected = {}
    for project in projects:
        expected.setdefault(project.name, 0)
        for _ in range(10):
            entry = JournalEntryFactory.create(name=project.name)
            if entry.id > expected[project.name]:
                expected[project.name] = entry.id
    assert xmlrpc.list_packages_with_serial(db_request) == expected


def test_package_hosting_mode_shows_none(db_request):
    assert xmlrpc.package_hosting_mode(db_request, "nope") is None


def test_package_hosting_mode_results(db_request):
    project = ProjectFactory.create(hosting_mode="pypi-explicit")
    assert xmlrpc.package_hosting_mode(db_request, project.name) == \
        "pypi-explicit"


def test_user_packages(db_request):
    user = UserFactory.create()
    other_user = UserFactory.create()
    owned_projects = [ProjectFactory.create() for _ in range(5)]
    maintained_projects = [ProjectFactory.create() for _ in range(5)]
    unowned_projects = [ProjectFactory.create() for _ in range(5)]
    for project in owned_projects:
        RoleFactory.create(project=project, user=user)
    for project in maintained_projects:
        RoleFactory.create(project=project, user=user, role_name="Maintainer")
    for project in unowned_projects:
        RoleFactory.create(project=project, user=other_user)

    assert set(xmlrpc.user_packages(db_request, user.username)) == set([
        ("Owner", p.name)
        for p in sorted(owned_projects, key=lambda x: x.name)
    ] + [
        ("Maintainer", p.name)
        for p in sorted(maintained_projects, key=lambda x: x.name)
    ])


@pytest.mark.parametrize("num", [None, 1, 5])
def test_top_packages(num):
    with pytest.raises(xmlrpc.XMLRPCWrappedError) as exc:
        xmlrpc.top_packages(pretend.stub(), num)

    assert exc.value.faultString == \
        "RuntimeError: This API has been removed. Please Use BigQuery instead."


def test_package_releases(db_request):
    project1 = ProjectFactory.create()
    releases1 = [ReleaseFactory.create(project=project1) for _ in range(10)]
    project2 = ProjectFactory.create()
    [ReleaseFactory.create(project=project2) for _ in range(10)]
    result = xmlrpc.package_releases(db_request, project1.name)
    assert result == [
        r.version
        for r in sorted(releases1, key=lambda x: x._pypi_ordering)
    ]


def test_release_data_no_project(db_request):
    assert xmlrpc.release_data(db_request, "foo", "1.0") == {}


def test_release_data_no_release(db_request):
    project = ProjectFactory.create()
    assert xmlrpc.release_data(db_request, project.name, "1.0") == {}


def test_release_data(db_request):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)

    svc = pretend.stub(
        get_daily_stats=pretend.call_recorder(lambda n: 10),
        get_weekly_stats=pretend.call_recorder(lambda n: 70),
        get_monthly_stats=pretend.call_recorder(lambda n: 300),
    )
    db_request.find_service = pretend.call_recorder(lambda s: svc)

    urls = [pretend.stub(), pretend.stub()]
    urls_iter = iter(urls)
    db_request.route_url = pretend.call_recorder(
        lambda r, **kw: next(urls_iter)
    )

    assert xmlrpc.release_data(db_request, project.name, release.version) == {
        "name": release.project.name,
        "version": release.version,
        "stable_version": release.project.stable_version,
        "bugtrack_url": release.project.bugtrack_url,
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
        "description": release.description,
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
        "_pypi_hidden": release._pypi_hidden,
        "downloads": {
            "last_day": 10,
            "last_week": 70,
            "last_month": 300,
        },
    }
    assert db_request.find_service.calls == [
        pretend.call(IDownloadStatService),
    ]
    assert svc.get_daily_stats.calls == [pretend.call(project.name)]
    assert svc.get_weekly_stats.calls == [pretend.call(project.name)]
    assert svc.get_monthly_stats.calls == [pretend.call(project.name)]
    db_request.route_url.calls == [
        pretend.call("packaging.project", name=project.name),
        pretend.call(
            "packaging.release",
            name=project.name,
            version=release.version,
        ),
    ]


def test_release_urls(db_request):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    file_ = FileFactory.create(
        release=release,
        filename="{}-{}.tar.gz".format(project.name, release.version),
        python_version="source",
    )

    urls = [pretend.stub()]
    urls_iter = iter(urls)
    db_request.route_url = pretend.call_recorder(
        lambda r, **kw: next(urls_iter)
    )

    assert xmlrpc.release_urls(db_request, project.name, release.version) == [
        {
            "filename": file_.filename,
            "packagetype": file_.packagetype,
            "python_version": file_.python_version,
            "size": file_.size,
            "md5_digest": file_.md5_digest,
            "digests": {
                "md5": file_.md5_digest,
                "sha256": file_.sha256_digest,
            },
            "has_sig": file_.has_signature,
            "upload_time": file_.upload_time,
            "comment_text": file_.comment_text,
            "downloads": -1,
            "url": urls[0],
        }
    ]
    assert db_request.route_url.calls == [
        pretend.call("packaging.file", path=file_.path),
    ]


def test_package_roles(db_request):
    project1, project2 = ProjectFactory.create(), ProjectFactory.create()
    owners1 = [RoleFactory.create(project=project1) for _ in range(3)]
    for _ in range(3):
        RoleFactory.create(project=project2)
    maintainers1 = [
        RoleFactory.create(project=project1, role_name="Maintainer")
        for _ in range(3)
    ]
    for _ in range(3):
        RoleFactory.create(project=project2, role_name="Maintainer")
    result = xmlrpc.package_roles(db_request, project1.name)
    assert result == [
        (r.role_name, r.user.username)
        for r in (
            sorted(owners1, key=lambda x: x.user.username.lower()) +
            sorted(maintainers1, key=lambda x: x.user.username.lower())
        )
    ]


def test_changelog_last_serial_none(db_request):
    assert xmlrpc.changelog_last_serial(db_request) is None


def test_changelog_last_serial(db_request):
    projects = [ProjectFactory.create() for _ in range(10)]
    entries = []
    for project in projects:
        for _ in range(10):
            entries.append(JournalEntryFactory.create(name=project.name))

    expected = max(e.id for e in entries)

    assert xmlrpc.changelog_last_serial(db_request) == expected


def test_changelog_since_serial(db_request):
    projects = [ProjectFactory.create() for _ in range(10)]
    entries = []
    for project in projects:
        for _ in range(10):
            entries.append(JournalEntryFactory.create(name=project.name))

    expected = [
        (
            e.name,
            e.version,
            int(
                e.submitted_date
                 .replace(tzinfo=datetime.timezone.utc)
                 .timestamp()
            ),
            e.action,
            e.id,
        )
        for e in entries
    ][int(len(entries) / 2):]

    serial = entries[int(len(entries) / 2) - 1].id

    assert xmlrpc.changelog_since_serial(db_request, serial) == expected


@pytest.mark.parametrize("with_ids", [True, False, None])
def test_changelog(db_request, with_ids):
    projects = [ProjectFactory.create() for _ in range(10)]
    entries = []
    for project in projects:
        for _ in range(10):
            entries.append(JournalEntryFactory.create(name=project.name))

    entries = sorted(entries, key=lambda x: x.submitted_date)

    since = int(
        entries[int(len(entries) / 2)].submitted_date
                                      .replace(tzinfo=datetime.timezone.utc)
                                      .timestamp()
    )

    expected = [
        (
            e.name,
            e.version,
            int(
                e.submitted_date
                 .replace(tzinfo=datetime.timezone.utc)
                 .timestamp()
            ),
            e.action,
            e.id,
        )
        for e in entries
        if (e.submitted_date.replace(
            tzinfo=datetime.timezone.utc).timestamp() > since)
    ]

    if not with_ids:
        expected = [e[:-1] for e in expected]

    extra_args = []
    if with_ids is not None:
        extra_args.append(with_ids)

    assert xmlrpc.changelog(db_request, since - 1, *extra_args) == expected


def test_browse(db_request):
    classifiers = [
        Classifier(classifier="Environment :: Other Environment"),
        Classifier(classifier="Development Status :: 5 - Production/Stable"),
        Classifier(classifier="Programming Language :: Python"),
    ]
    for classifier in classifiers:
        db_request.db.add(classifier)

    projects = [ProjectFactory.create() for _ in range(3)]
    releases = []
    for project in projects:
        for _ in range(10):
            releases.append(
                ReleaseFactory.create(
                    project=project,
                    _classifiers=[classifiers[0]]
                ),
            )

    releases = sorted(releases, key=lambda x: (x.project.name, x.version))

    expected_release = releases[0]
    expected_release._classifiers = classifiers

    assert set(xmlrpc.browse(
        db_request,
        ["Environment :: Other Environment"]
    )) == {(r.name, r.version) for r in releases}
    assert set(xmlrpc.browse(
        db_request,
        [
            "Environment :: Other Environment",
            "Development Status :: 5 - Production/Stable",
        ],
    )) == {(expected_release.name, expected_release.version)}
    assert set(xmlrpc.browse(
        db_request,
        [
            "Environment :: Other Environment",
            "Development Status :: 5 - Production/Stable",
            "Programming Language :: Python",
        ],
    )) == {(expected_release.name, expected_release.version)}
    assert set(xmlrpc.browse(
        db_request,
        [
            "Development Status :: 5 - Production/Stable",
            "Programming Language :: Python",
        ],
    )) == {(expected_release.name, expected_release.version)}
