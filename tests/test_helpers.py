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

import fnmatch

import pretend
import pytest

from warehouse.helpers import (gravatar_url, url_for, static_url,
                               is_valid_json_callback_name)


@pytest.mark.parametrize(("email", "kwargs", "expected"), [
    (
        "test-user@example.com",
        {},
        ("https://secure.gravatar.com/avatar/3664adb7d1eea0bd7d0b134577663889"
         "?size=80"),
    ),
    (
        "test-user@example.com",
        {"size": 1000},
        ("https://secure.gravatar.com/avatar/3664adb7d1eea0bd7d0b134577663889"
         "?size=1000"),
    ),
    (
        None,
        {},
        ("https://secure.gravatar.com/avatar/d41d8cd98f00b204e9800998ecf8427e"
         "?size=80"),
    )
])
def test_gravatar_url(email, kwargs, expected):
    assert gravatar_url(email, **kwargs) == expected


@pytest.mark.parametrize(("external",), [(False,), (True,)])
def test_url_for(external):
    request = pretend.stub(
        url_adapter=pretend.stub(
            build=pretend.call_recorder(lambda *a, **k: "/foo/"),
        ),
    )

    assert url_for(
        request,
        "warehouse.test",
        foo="bar",
        _force_external=external,
    ) == "/foo/"

    assert request.url_adapter.build.calls == [
        pretend.call(
            "warehouse.test",
            {"foo": "bar"},
            force_external=external,
        ),
    ]


@pytest.mark.parametrize(("filename", "expected"), [
    ("css/warehouse.css", "/static/css/warehouse-*.css"),
    ("css/fake.css", "/static/css/fake.css"),
    ("warehouse/css/warehouse.css", "/static/warehouse/css/warehouse.css"),
])
def test_static_url(filename, expected):
    app = pretend.stub(
        config=pretend.stub(
            urls=pretend.stub(
                assets="/static/",
            ),
        ),
    )

    assert fnmatch.fnmatch(static_url(app, filename), expected)


@pytest.mark.parametrize(("callback", "expected"), [
    ("", False),
    ("too long" * 50, False),
    ("somehack()", False),
    ("break", False),
    ("valid", True),
])
def test_is_valid_json_callback_name(callback, expected):
    assert is_valid_json_callback_name(callback) == expected
