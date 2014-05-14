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

from unittest import mock

import pretend

from warehouse.views import index

from .lib.db import db_fixtures


@db_fixtures(
    "projects.foobar",
    "projects.Dinner",

    "releases.foobar-1-0",
    "releases.foobar-1-1",
    "releases.Dinner-1-0",

    "files.foobar-1-0-tar-gz",
    "files.foobar-1-1-tar-gz",
    "files.Dinner-1-0-tar-gz",
    "files.Dinner-1-0-py2-py3-none-any-whl",
)
def test_index(dbapp, db_fixtures):
    request = pretend.stub()

    resp = index(dbapp, request)

    assert resp.response.template.name == "index.html"
    assert resp.response.context == {
        "project_count": 2,
        "download_count": 6448,
        "recently_updated": [
            {
                "name": "foobar",
                "version": "1.1",
                "summary": "This is a summary for foobar 1.1",
                "created": mock.ANY,
            },
            {
                "name": "Dinner",
                "version": "1.0",
                "summary": "This is a summary for Dinner 1.0",
                "created": mock.ANY,
            },
        ],
    }
