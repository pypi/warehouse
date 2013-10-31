# Copyright 2013 Donald Stufft
#
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import datetime
import os.path

import pretend
import pytest
import pytz

from warehouse.accounts.tables import users, emails
from warehouse.packaging.models import Project, FileURL, log
from warehouse.packaging.tables import (
    packages, releases, release_files, description_urls, journals, classifiers,
    release_classifiers, release_dependencies, roles,
)


@pytest.mark.parametrize("projects", [
    ["foo", "bar", "zap"],
    ["fail", "win", "YeS"],
])
def test_all_projects(projects, dbapp):
    # Insert some data into the database
    for project in projects:
        dbapp.engine.execute(packages.insert().values(name=project))

    all_projects = [
        Project(p) for p in sorted(projects, key=lambda x: x.lower())
    ]
    assert dbapp.models.packaging.all_projects() == all_projects


@pytest.mark.parametrize(("name", "normalized"), [
    ("foo_bar", "foo-bar"),
    ("Bar", "bar"),
])
def test_get_project(name, normalized, dbapp):
    # prepare database
    dbapp.engine.execute(
        packages.insert().values(name=name, normalized_name=normalized)
    )

    assert dbapp.models.packaging.get_project(normalized) == Project(name)


def test_get_project_missing(dbapp):
    assert dbapp.models.packaging.get_project("missing") is None


def test_get_projects_for_user(dbapp):
    dbapp.engine.execute(users.insert().values(
        password="!",
        username="test-user",
        name="Test User",
        last_login=datetime.datetime.utcnow(),
        is_active=True,
        is_superuser=False,
        is_staff=False,
    ))
    dbapp.engine.execute(packages.insert().values(name="test-project"))
    dbapp.engine.execute(releases.insert().values(
        name="test-project",
        version="1.0",
        summary="test summmary",
        _pypi_ordering=1,
    ))
    dbapp.engine.execute(releases.insert().values(
        name="test-project",
        version="2.0",
        summary="test summmary 2.0",
        _pypi_ordering=2,
    ))
    dbapp.engine.execute(roles.insert().values(
        package_name="test-project",
        user_name="test-user",
        role_name="Owner",
    ))

    assert dbapp.models.packaging.get_projects_for_user("test-user") == [
        {"name": "test-project", "summary": "test summmary 2.0"},
    ]


def test_get_projects_for_user_missing(dbapp):
    assert dbapp.models.packaging.get_projects_for_user("missing") == []


def test_get_users_for_project(dbapp):
    dbapp.engine.execute(users.insert().values(
        id=1,
        password="!",
        username="test-user",
        name="Test User",
        last_login=datetime.datetime.utcnow(),
        is_active=True,
        is_superuser=False,
        is_staff=False,
    ))
    dbapp.engine.execute(users.insert().values(
        id=2,
        password="!",
        username="a-test-user",
        name="Test User",
        last_login=datetime.datetime.utcnow(),
        is_active=True,
        is_superuser=False,
        is_staff=False,
    ))
    dbapp.engine.execute(users.insert().values(
        id=3,
        password="!",
        username="test-user2",
        name="Test User2",
        last_login=datetime.datetime.utcnow(),
        is_active=True,
        is_superuser=False,
        is_staff=False,
    ))
    dbapp.engine.execute(emails.insert().values(
        user_id=3,
        email="test@example.com",
        primary=True,
        verified=True,
    ))
    dbapp.engine.execute(packages.insert().values(name="test-project"))
    dbapp.engine.execute(roles.insert().values(
        package_name="test-project",
        user_name="test-user",
        role_name="Owner",
    ))
    dbapp.engine.execute(roles.insert().values(
        package_name="test-project",
        user_name="test-user2",
        role_name="Maintainer",
    ))
    dbapp.engine.execute(roles.insert().values(
        package_name="test-project",
        user_name="a-test-user",
        role_name="Maintainer",
    ))

    assert dbapp.models.packaging.get_users_for_project("test-project") == [
        {"username": "test-user", "email": None},
        {"username": "a-test-user", "email": None},
        {"username": "test-user2", "email": "test@example.com"},
    ]


def test_get_users_for_project_missing(dbapp):
    assert dbapp.models.packaging.get_users_for_project("test-project") == []


@pytest.mark.parametrize(("name", "mode"), [
    ("foo", "pypi-explicit"),
    ("bar", "pypi-scrape"),
    ("wat", "pypi-scrape-crawl"),
])
def test_get_hosting_mode(name, mode, dbapp):
    # prepare database
    dbapp.engine.execute(
        packages.insert().values(name=name, hosting_mode=mode)
    )

    assert dbapp.models.packaging.get_hosting_mode(name) == mode


@pytest.mark.parametrize(("name", "attrs"), [
    ("foo", [
        {"version": "1.0", "home_page": "https://example.com/v1/home/"},
        {"version": "2.0", "download_url": "https://example.com/v2/download"},
        {
            "version": "3.0",
            "home_page": "https://example.com/v3/home/",
            "download_url": "https://example.com/v3/download",
        },
    ]),
])
def test_get_release_urls(name, attrs, dbapp):
    # prepare database
    dbapp.engine.execute(packages.insert().values(name=name))
    for data in attrs:
        dbapp.engine.execute(
            releases.insert().values(name=name, **data)
        )

    assert dbapp.models.packaging.get_release_urls(name) == {
        a["version"]: (a.get("home_page"), a.get("download_url"))
        for a in attrs
    }


@pytest.mark.parametrize(("name", "urls"), [
    ("foo", [
        "https://example.com/1/",
        "https://example.com/3/",
        "https://example.com/2/",
        "https://example.com/5/",
        "https://example.com/3/",
    ]),
])
def test_get_external_urls(name, urls, dbapp):
    # prepare database
    for url in urls:
        dbapp.engine.execute(
            description_urls.insert().values(name=name, url=url)
        )

    assert dbapp.models.packaging.get_external_urls(name) == sorted(set(urls))


@pytest.mark.parametrize(("name", "values", "urls"), [
    (
        "test-package",
        [
            {
                "filename": "test-package-1.0.tar.gz",
                "python_version": "any",
                "md5_digest": "d41d8cd98f00b204e9800998ecf8427e",
            },
            {
                "filename": "test-package-2.0.tar.gz",
                "python_version": "any",
                "md5_digest": "d41d8cd98f00b204e9800998ecf8427f",
            },
        ],
        [
            (
                "test-package-1.0.tar.gz",
                ("../../packages/any/t/test-package/test-package-1.0.tar.gz"
                 "#md5=d41d8cd98f00b204e9800998ecf8427e"),
            ),
            (
                "test-package-2.0.tar.gz",
                ("../../packages/any/t/test-package/test-package-2.0.tar.gz"
                 "#md5=d41d8cd98f00b204e9800998ecf8427f"),
            ),
        ],
    ),
])
def test_get_file_urls(name, values, urls, dbapp):
    # prepare db
    dbapp.engine.execute(packages.insert().values(name=name))
    for value in values:
        dbapp.engine.execute(release_files.insert().values(name=name, **value))

    assert dbapp.models.packaging.get_file_urls(name) == [
        FileURL(f, u) for f, u in sorted(set(urls), reverse=True)
    ]


@pytest.mark.parametrize(("name", "filename"), [
    ("foo", "foo-1.0.tar.gz"),
])
def test_get_project_for_filename(name, filename, dbapp):
    # prepare database
    dbapp.engine.execute(
        release_files.insert().values(name=name, filename=filename)
    )

    assert (dbapp.models.packaging.get_project_for_filename(filename)
            == Project(name))


@pytest.mark.parametrize(("filename", "md5"), [
    ("foo-1.0.tar.gz", "d41d8cd98f00b204e9800998ecf8427f"),
])
def test_get_filename_md5(filename, md5, dbapp):
    # prepare database
    dbapp.engine.execute(
        release_files.insert().values(filename=filename, md5_digest=md5)
    )

    assert dbapp.models.packaging.get_filename_md5(filename) == md5


@pytest.mark.parametrize(("name", "serial"), [
    ("foo", 1234567),
    (None, 2345553),
])
def test_get_last_serial(name, serial, dbapp):
    dbapp.engine.execute(journals.insert().values(id=serial, name=name))

    assert dbapp.models.packaging.get_last_serial(name) == serial


def test_get_project_versions(dbapp):
    dbapp.engine.execute(packages.insert().values(name="test-project"))
    dbapp.engine.execute(releases.insert().values(
        name="test-project",
        version="2.0",
        _pypi_ordering=2,
    ))
    dbapp.engine.execute(releases.insert().values(
        name="test-project",
        version="1.0",
        _pypi_ordering=1,
    ))
    dbapp.engine.execute(releases.insert().values(
        name="test-project",
        version="3.0",
        _pypi_ordering=3,
    ))

    assert dbapp.models.packaging.get_project_versions("test-project") == [
        "3.0",
        "2.0",
        "1.0",
    ]


def test_get_release(dbapp):
    created = pytz.utc.localize(datetime.datetime.utcnow())

    dbapp.engine.execute(packages.insert().values(name="test-project"))
    dbapp.engine.execute(releases.insert().values(
        created=created,
        name="test-project",
        version="1.0",
        author="John Doe",
        author_email="john.doe@example.com",
        maintainer="Jane Doe",
        maintainer_email="jane.doe@example.com",
        home_page="https://example.com/",
        license="Apache License v2.0",
        summary="A Test Project",
        description="A Longer Test Project",
        keywords="foo,bar,wat",
        platform="All",
        download_url="https://example.com/downloads/test-project-1.0.tar.gz",
        _pypi_ordering=1,
    ))
    dbapp.engine.execute(releases.insert().values(
        created=created,
        name="test-project",
        version="2.0",
        author="John Doe",
        author_email="john.doe@example.com",
        maintainer="Jane Doe",
        maintainer_email="jane.doe@example.com",
        home_page="https://example.com/",
        license="Apache License v2.0",
        summary="A Test Project",
        description="A Longer Test Project",
        keywords="foo,bar,wat",
        platform="All",
        download_url="https://example.com/downloads/test-project-1.0.tar.gz",
        _pypi_ordering=2,
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="1.0",
        kind=4,
        specifier="requests (>=2.0)",
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="2.0",
        kind=4,
        specifier="requests (>=2.0)",
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="1.0",
        kind=5,
        specifier="test-project-old",
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="2.0",
        kind=5,
        specifier="test-project-old",
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="1.0",
        kind=8,
        specifier="Repository,git://git.example.com/",
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="2.0",
        kind=8,
        specifier="Repository,git://git.example.com/",
    ))

    test_release = dbapp.models.packaging.get_release("test-project", "1.0")

    assert test_release == {
        "name": "test-project",
        "version": "1.0",
        "author": "John Doe",
        "author_email": "john.doe@example.com",
        "maintainer": "Jane Doe",
        "maintainer_email": "jane.doe@example.com",
        "home_page": "https://example.com/",
        "license": "Apache License v2.0",
        "summary": "A Test Project",
        "description": "A Longer Test Project",
        "keywords": "foo,bar,wat",
        "platform": "All",
        "download_url": ("https://example.com/downloads/"
                         "test-project-1.0.tar.gz"),
        "requires_dist": ["requests (>=2.0)"],
        "provides_dist": ["test-project-old"],
        "project_url": {"Repository": "git://git.example.com/"},
        "created": created,
    }


def test_get_releases(dbapp):
    created = pytz.utc.localize(datetime.datetime.utcnow())

    dbapp.engine.execute(packages.insert().values(name="test-project"))
    dbapp.engine.execute(releases.insert().values(
        created=created,
        name="test-project",
        version="1.0",
        author="John Doe",
        author_email="john.doe@example.com",
        maintainer="Jane Doe",
        maintainer_email="jane.doe@example.com",
        home_page="https://example.com/",
        license="Apache License v2.0",
        summary="A Test Project",
        description="A Longer Test Project",
        keywords="foo,bar,wat",
        platform="All",
        download_url="https://example.com/downloads/test-project-1.0.tar.gz",
        _pypi_ordering=1,
    ))
    dbapp.engine.execute(releases.insert().values(
        created=created,
        name="test-project",
        version="2.0",
        author="John Doe",
        author_email="john.doe@example.com",
        maintainer="Jane Doe",
        maintainer_email="jane.doe@example.com",
        home_page="https://example.com/",
        license="Apache License v2.0",
        summary="A Test Project",
        description="A Longer Test Project",
        keywords="foo,bar,wat",
        platform="All",
        download_url="https://example.com/downloads/test-project-1.0.tar.gz",
        _pypi_ordering=2,
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="1.0",
        kind=4,
        specifier="requests (>=2.0)",
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="2.0",
        kind=4,
        specifier="requests (>=2.0)",
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="1.0",
        kind=5,
        specifier="test-project-old",
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="2.0",
        kind=5,
        specifier="test-project-old",
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="1.0",
        kind=8,
        specifier="Repository,git://git.example.com/",
    ))
    dbapp.engine.execute(release_dependencies.insert().values(
        name="test-project",
        version="2.0",
        kind=8,
        specifier="Repository,git://git.example.com/",
    ))

    assert dbapp.models.packaging.get_releases("test-project") == [
        {
            "name": "test-project",
            "version": "2.0",
            "author": "John Doe",
            "author_email": "john.doe@example.com",
            "maintainer": "Jane Doe",
            "maintainer_email": "jane.doe@example.com",
            "home_page": "https://example.com/",
            "license": "Apache License v2.0",
            "summary": "A Test Project",
            "keywords": "foo,bar,wat",
            "platform": "All",
            "download_url": ("https://example.com/downloads/"
                             "test-project-1.0.tar.gz"),
            "created": created,
        },
        {
            "name": "test-project",
            "version": "1.0",
            "author": "John Doe",
            "author_email": "john.doe@example.com",
            "maintainer": "Jane Doe",
            "maintainer_email": "jane.doe@example.com",
            "home_page": "https://example.com/",
            "license": "Apache License v2.0",
            "summary": "A Test Project",
            "keywords": "foo,bar,wat",
            "platform": "All",
            "download_url": ("https://example.com/downloads/"
                             "test-project-1.0.tar.gz"),
            "created": created,
        },
    ]


@pytest.mark.parametrize("exists", [True, False])
def test_get_documentation_url(exists, dbapp, monkeypatch):
    os_exists = pretend.call_recorder(lambda p: exists)

    monkeypatch.setattr(os.path, "exists", os_exists)

    docurl = dbapp.models.packaging.get_documentation_url("test-project")

    if exists:
        assert docurl == "https://pythonhosted.org/test-project/"
    else:
        assert docurl is None

    assert os_exists.calls == [
        pretend.call("data/packagedocs/test-project/index.html"),
    ]


def test_get_bugtrack_url(dbapp):
    dbapp.engine.execute(packages.insert().values(
        name="test-project",
        bugtrack_url="https://example.com/issues/",
    ))

    bugtracker = dbapp.models.packaging.get_bugtrack_url("test-project")

    assert bugtracker == "https://example.com/issues/"


def test_get_classifiers(dbapp):
    dbapp.engine.execute(packages.insert().values(name="test-project"))
    dbapp.engine.execute(releases.insert().values(
        name="test-project",
        version="1.0",
    ))
    dbapp.engine.execute(classifiers.insert().values(
        id=1,
        classifier="Test :: Classifier",
    ))
    dbapp.engine.execute(release_classifiers.insert().values(
        name="test-project",
        version="1.0",
        trove_id=1,
    ))

    test_classifiers = dbapp.models.packaging.get_classifiers(
        "test-project",
        "1.0",
    )

    assert test_classifiers == ["Test :: Classifier"]


@pytest.mark.parametrize("pgp", [True, False])
def test_get_downloads(pgp, dbapp, monkeypatch):
    dbapp.engine.execute(packages.insert().values(name="test-project"))
    dbapp.engine.execute(releases.insert().values(
        name="test-project",
        version="1.0",
    ))
    dbapp.engine.execute(release_files.insert().values(
        name="test-project",
        version="1.0",
        filename="test-project-1.0.tar.gz",
        python_version="source",
        packagetype="sdist",
        md5_digest="0cc175b9c0f1b6a831c399e269772661",
        downloads=10,
        upload_time=datetime.datetime(
            year=2013, month=1, day=30,
            tzinfo=pytz.utc,
        ),
    ))

    def os_exists():
        yield       # start
        yield True  # whether download file exists
        yield pgp   # whether .asc pgp file exists
    f = os_exists().send
    f(None)     # start it off
    os_exists = pretend.call_recorder(f)

    monkeypatch.setattr(os.path, "exists", os_exists)
    monkeypatch.setattr(os.path, "getsize", lambda x: 10)

    dbapp.config.paths.packages = "fake"

    downloads = dbapp.models.packaging.get_downloads("test-project", "1.0")

    pgp_url = "/packages/source/t/test-project/test-project-1.0.tar.gz.asc"

    assert downloads == [
        {
            "name": "test-project",
            "version": "1.0",
            "filename": "test-project-1.0.tar.gz",
            "filepath": "fake/source/t/test-project/test-project-1.0.tar.gz",
            "comment_text": None,
            "downloads": 10,
            "upload_time": datetime.datetime(
                year=2013, month=1, day=30,
                tzinfo=pytz.utc,
            ),
            "python_version": "source",
            "md5_digest": "0cc175b9c0f1b6a831c399e269772661",
            "url": "/packages/source/t/test-project/test-project-1.0.tar.gz",
            "packagetype": "sdist",
            "size": 10,
            "pgp_url": pgp_url if pgp else None,
        },
    ]
    assert os_exists.calls == [
        pretend.call(downloads[0]["filepath"]),
        pretend.call(downloads[0]["filepath"] + ".asc")
    ]


def test_get_downloads_missing(dbapp, monkeypatch):
    dbapp.engine.execute(packages.insert().values(name="test-project"))
    dbapp.engine.execute(releases.insert().values(
        name="test-project",
        version="1.0",
    ))
    dbapp.engine.execute(release_files.insert().values(
        name="test-project",
        version="1.0",
        filename="test-project-1.0.tar.gz",
        python_version="source",
        packagetype="sdist",
        md5_digest="0cc175b9c0f1b6a831c399e269772661",
        downloads=10,
        upload_time=datetime.datetime(year=2013, month=1, day=30),
    ))

    # file does not exist
    os_exists = pretend.call_recorder(lambda p: False)

    # we match the specific arguments below - no need forcing them here as well
    log_error = pretend.call_recorder(lambda *a: None)

    monkeypatch.setattr(os.path, "exists", os_exists)
    # log from warehouse.packaging.models
    monkeypatch.setattr(log, "error", log_error)

    dbapp.config.paths.packages = "fake"

    downloads = dbapp.models.packaging.get_downloads("test-project", "1.0")

    assert downloads == []
    filepath = "fake/source/t/test-project/test-project-1.0.tar.gz"
    assert os_exists.calls == [pretend.call(filepath)]

    # actual error message may vary, so just assert that the logging was called
    assert log_error.calls == [
        pretend.call(
            "%s missing for package %s %s",
            filepath,
            "test-project",
            "1.0",
        ),
    ]


def test_get_download_counts(dbapp):
    mget = pretend.call_recorder(lambda *k: ["10", "20"])
    dbapp.models.packaging.redis = pretend.stub(mget=mget)

    counts = dbapp.models.packaging.get_download_counts("test-project")

    assert counts == {"last_day": 30, "last_week": 30, "last_month": 30}
    assert len(mget.calls) == 3
