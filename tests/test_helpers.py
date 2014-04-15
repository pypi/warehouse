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

import fnmatch

import pretend
import pytest

from warehouse.helpers import gravatar_url, static_url, csrf_token


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
    ),
])
def test_gravatar_url(email, kwargs, expected):
    assert gravatar_url(email, **kwargs) == expected


@pytest.mark.parametrize(("filename", "expected"), [
    ("css/warehouse.css", "/static/css/warehouse.*.css"),
    ("css/fake.css", "/static/css/fake.css"),
])
def test_static_url(filename, expected, warehouse_app):
    with warehouse_app.test_request_context('/'):
        assert fnmatch.fnmatch(static_url(filename), expected)


@pytest.mark.parametrize("request", [
    pretend.stub(),
    pretend.stub(_csrf=False),
])
def test_csrf_token_no_csrf(request):
    with pytest.raises(ValueError):
        csrf_token(request)


def test_csrf_token():
    assert (
        csrf_token(pretend.stub(_csrf=True, _session={"user.csrf": "123456"}))
        == "<input type=hidden name=csrf_token value=\"123456\">"
    )
