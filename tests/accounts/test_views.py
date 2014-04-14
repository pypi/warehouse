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

from flask import session

from werkzeug.exceptions import NotFound

from warehouse.accounts import views
from warehouse.accounts.views import user_profile, login, logout


def test_user_profile_missing_user(warehouse_app):
    warehouse_app.db = pretend.stub(
        accounts=pretend.stub(
            get_user=pretend.call_recorder(lambda user: None),
        ),
    )

    username = "test-user"

    with warehouse_app.test_request_context():
        with pytest.raises(NotFound):
            user_profile(username=username)

    assert warehouse_app.db.accounts.get_user.calls == [
        pretend.call("test-user")
    ]


def test_user_profile_redirects(warehouse_app):
    warehouse_app.warehouse_config = pretend.stub(
        cache=pretend.stub(
            browser=False,
            varnish=False,
        ),
    )
    warehouse_app.db = pretend.stub(
        accounts=pretend.stub(
            get_user=pretend.call_recorder(
                lambda user: {"username": "test-User"},
            ),
        ),
    )

    username = "test-user"

    with warehouse_app.test_request_context():
        resp = user_profile(username=username)

    assert resp.status_code == 301
    assert resp.headers["Location"] == "/user/test-User"

    assert warehouse_app.db.accounts.get_user.calls == [
        pretend.call("test-user")
    ]


def test_user_profile_renders(monkeypatch, warehouse_app):
    warehouse_app.warehouse_config = pretend.stub(
        cache=pretend.stub(
            browser=False,
            varnish=False,
        ),
    )
    warehouse_app.db = pretend.stub(
        accounts=pretend.stub(
            get_user=pretend.call_recorder(
                lambda user: {"username": "test-user"},
            ),
        ),
        packaging=pretend.stub(
            get_projects_for_user=pretend.call_recorder(
                lambda user: None,
            ),
        ),
    )

    response = pretend.stub(
        status_code=200,
        headers={},
        cache_control=pretend.stub(),
        surrogate_control=pretend.stub(),
    )
    render_template = pretend.call_recorder(lambda *args, **ctx: response)
    monkeypatch.setattr(views, "render_template", render_template)

    username = "test-user"
    with warehouse_app.test_request_context():
        resp = user_profile(username=username)

    assert resp.status_code == 200

    assert warehouse_app.db.accounts.get_user.calls == [
        pretend.call("test-user")
    ]
    assert warehouse_app.db.packaging.get_projects_for_user.calls == [
        pretend.call("test-user"),
    ]

    assert render_template.calls == [
        pretend.call(
            'accounts/profile.html',
            projects=None,
            user={'username': username}
        ),
    ]


def test_user_login_get(monkeypatch, warehouse_app):
    warehouse_app.warehouse_config = pretend.stub()
    warehouse_app.db = pretend.stub(
        accounts=pretend.stub(
            user_authenticate=pretend.stub(),
        )
    )
    warehouse_app.testing = True

    render_template = pretend.call_recorder(lambda *args, **ctx: '')
    monkeypatch.setattr(views, "render_template", render_template)

    with warehouse_app.test_client() as c:
        resp = c.get('/account/login')

    assert resp.status_code == 200
    assert render_template.calls == [
        pretend.call("accounts/login.html", form=mock.ANY, next=None),
    ]


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
def test_user_login_post_valid(
        form, values, session, location, warehouse_app, monkeypatch):
    warehouse_app.db = pretend.stub(
        accounts=pretend.stub(
            get_user_id=lambda username: 9001,
            user_authenticate=lambda user, password: True,
        ),
    )

    render_template = pretend.call_recorder(lambda *args, **ctx: '')
    monkeypatch.setattr(views, "render_template", render_template)

    with warehouse_app.test_request_context(
            method='POST', data=form, query_string=values):
        resp = login()

        assert resp.status_code == 303
        assert resp.headers["Location"] == location
        assert resp.headers.getlist("Set-Cookie") == ["username=test; Path=/"]


def test_user_logout_get(warehouse_app, monkeypatch):
    render_template = pretend.call_recorder(lambda *args, **ctx: '')
    monkeypatch.setattr(views, "render_template", render_template)

    with warehouse_app.test_client() as c:
        with c.session_transaction() as sess:
            sess['user.id'] = 1
        resp = c.get('/account/logout/')

    assert resp.status_code == 200
    assert render_template.calls == [
        pretend.call("accounts/logout.html", next=None),
    ]


@pytest.mark.parametrize(("values", "location"), [
    ({}, "/"),
    ({"next": "/wat/"}, "/wat/"),
])
def test_user_logout_post(values, location, warehouse_app, monkeypatch):
    render_template = pretend.call_recorder(lambda *args, **ctx: '')
    monkeypatch.setattr(views, "render_template", render_template)

    with warehouse_app.test_request_context(
            method='POST', query_string=values):
        resp = logout()
        assert session.deleted

    assert resp.status_code == 303
    assert resp.headers["Location"] == location
    assert resp.headers.getlist("Set-Cookie") == [
        "username=; Expires=Thu, 01-Jan-1970 00:00:00 GMT; Max-Age=0; Path=/",
    ]
