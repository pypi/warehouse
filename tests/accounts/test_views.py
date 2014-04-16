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
import pytest

from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import NotFound

from warehouse.accounts.views import user_profile, login, logout
from warehouse.sessions import Session


def test_user_profile_missing_user():
    app = pretend.stub(
        db=pretend.stub(
            accounts=pretend.stub(
                get_user=pretend.call_recorder(lambda user: None),
            ),
        ),
    )
    request = pretend.stub()

    username = "test-user"

    with pytest.raises(NotFound):
        user_profile(app, request, username=username)

    assert app.db.accounts.get_user.calls == [pretend.call("test-user")]


def test_user_profile_redirects():
    app = pretend.stub(
        config=pretend.stub(
            cache=pretend.stub(
                browser=False,
                varnish=False,
            ),
        ),
        db=pretend.stub(
            accounts=pretend.stub(
                get_user=pretend.call_recorder(
                    lambda user: {"username": "test-User"},
                ),
            ),
        ),
    )
    request = pretend.stub(
        url_adapter=pretend.stub(
            build=pretend.call_recorder(
                lambda *a, **kw: "/~test-User/",
            ),
        ),
    )

    username = "test-user"

    resp = user_profile(app, request, username=username)

    assert resp.status_code == 301
    assert resp.headers["Location"] == "/~test-User/"

    assert app.db.accounts.get_user.calls == [pretend.call("test-user")]

    assert request.url_adapter.build.calls == [
        pretend.call(
            "warehouse.accounts.views.user_profile",
            {"username": "test-User"},
            force_external=False,
        ),
    ]


def test_user_profile_renders(app):
    app.db = pretend.stub(
        accounts=pretend.stub(
            get_user=pretend.call_recorder(
                lambda user: {
                    "username": "test-user",
                    "email": "test@example.com",
                },
            ),
        ),
        packaging=pretend.stub(
            get_projects_for_user=pretend.call_recorder(lambda user: None),
        ),
    )

    request = pretend.stub()

    resp = user_profile(app, request, username="test-user")

    assert resp.status_code == 200
    assert resp.context == {
        "projects": None,
        "user": {
            "username": "test-user",
            "email": "test@example.com",
        },
    }

    assert app.db.accounts.get_user.calls == [pretend.call("test-user")]
    assert app.db.packaging.get_projects_for_user.calls == [
        pretend.call("test-user"),
    ]


def test_user_login_get(app):
    app.db = pretend.stub(
        accounts=pretend.stub(
            user_authenticate=pretend.stub(),
        ),
    )

    request = pretend.stub(
        method="GET",
        form=MultiDict(),
        values={},
        _session=Session({}, "1234", False),
    )

    resp = login(app, request)

    assert resp.status_code == 200
    assert resp.context == {
        "form": mock.ANY,
        "next": None,
    }


@pytest.mark.parametrize(("form", "values", "session", "location"), [
    ({"username": "test", "password": "p@ssw0rd"}, {}, {}, "/"),
    ({"username": "test", "password": "p@ssw0rd"}, {}, {"user.id": 100}, "/"),
    ({"username": "test", "password": "p@ssw0rd"}, {}, {"user.id": 9001}, "/"),
    (
        {"username": "test", "password": "p@ssw0rd"},
        {"next": "/wat/"},
        {},
        "/wat/",
    ),
    (
        {"username": "test", "password": "p@ssw0rd"},
        {"next": "/wat/"},
        {"user.id": 100},
        "/wat/",
    ),
    (
        {"username": "test", "password": "p@ssw0rd"},
        {"next": "/wat/"},
        {"user.id": 9001},
        "/wat/",
    ),
])
def test_user_login_post_valid(app, form, values, session, location):
    app.db = pretend.stub(
        accounts=pretend.stub(
            get_user_id=lambda username: 9001,
            user_authenticate=lambda user, password: True,
        ),
    )

    request = pretend.stub(
        method="POST",
        form=MultiDict(form),
        host="example.com",
        values=values,
        url_adapter=pretend.stub(
            build=lambda *a, **kw: "/",
        ),
        _session=Session(session, "1234", False),
    )

    resp = login(app, request)

    assert request.session["user.id"] == 9001
    assert resp.status_code == 303
    assert resp.headers["Location"] == location
    assert resp.headers.getlist("Set-Cookie") == ["username=test; Path=/"]


def test_user_logout_get(app):
    request = pretend.stub(
        method="GET",
        values={},
        _session=Session({"user.id": 1}, "1234", False),
    )

    resp = logout(app, request)

    assert resp.status_code == 200
    assert resp.template.name == "accounts/logout.html"
    assert resp.context == {"next": None}


@pytest.mark.parametrize(("values", "location"), [
    ({}, "/"),
    ({"next": "/wat/"}, "/wat/"),
])
def test_user_logout_post(values, location):
    app = pretend.stub(config=pretend.stub())
    request = pretend.stub(
        method="POST",
        host="example.com",
        values=values,
        url_adapter=pretend.stub(
            build=lambda *a, **kw: "/",
        ),
        _session=Session({"user.id": 1}, "1234", False),
    )

    resp = logout(app, request)

    assert resp.status_code == 303
    assert resp.headers["Location"] == location
    assert resp.headers.getlist("Set-Cookie") == [
        "username=; Expires=Thu, 01-Jan-1970 00:00:00 GMT; Max-Age=0; Path=/",
    ]
    assert request._session.deleted
