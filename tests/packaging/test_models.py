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

import pytest

from warehouse.packaging.models import Project, FileURL
from warehouse.packaging.tables import (
    packages, releases, release_files, description_urls, journals,
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
