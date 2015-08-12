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

import collections
import random

import pytest

from warehouse.legacy.api import xmlrpc

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    ProjectFactory, ReleaseFactory, FileFactory, RoleFactory,
    JournalEntryFactory,
)


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
    project = ProjectFactory.create()
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
def test_top_packages(db_request, num):
    projects = [ProjectFactory.create() for _ in range(10)]
    files = collections.Counter()
    for project in projects:
        releases = [ReleaseFactory.create(project=project) for _ in range(3)]
        for release in releases:
            file_ = FileFactory.create(
                release=release,
                filename="{}-{}.tar.gz".format(project.name, release.version),
                downloads=random.randint(0, 1000),
            )
            files[project.name] += file_.downloads

    assert set(xmlrpc.top_packages(db_request, num)) == \
        set(files.most_common(num))


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
