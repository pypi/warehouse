# Copyright 2014 Donald Stufft
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
import pretend
import pytest

from flask import session
from werkzeug.exceptions import SecurityError

from warehouse.csrf import (
    _verify_csrf_origin, _verify_csrf_token, _ensure_csrf_token, csrf_protect,
    csrf_exempt, csrf_cycle, handle_csrf,
)
from warehouse.http import Response


class TestHandleCSRF:

    def test_csrf_ensured(self, warehouse_app):
        """
        Ensures that the csrf token is there in the response
        """
        @warehouse_app.route('/csrf-protected-view')
        @csrf_protect
        def csrf_protected_view():
            return "Hello World"

        assert csrf_protected_view._csrf is True

        with warehouse_app.test_client() as c:
            c.get('/csrf-protected-view')
            assert "user.csrf" in session

    def test_csrf_already_ensured(self, warehouse_app):
        """
        If a CSRF Token is already in the session, it should be there in
        the request session
        """
        @warehouse_app.route('/csrf-protected-view')
        @csrf_protect
        def csrf_protected_view():
            return "Hello World"

        assert csrf_protected_view._csrf is True

        with warehouse_app.test_client() as c:
            with c.session_transaction() as sess:
                sess['user.csrf'] = '1234'

            c.get('/csrf-protected-view')
            assert "user.csrf" in session
            assert session == {"user.csrf": "1234"}

    @pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "TRACE"])
    def test_csrf_allows_safe(self, method):
        view = lambda: Response()
        req = pretend.stub(session={}, method=method)

        handle_csrf(req, view)

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_csrf_disallows_unsafe(self, method):
        view = lambda: Response()
        req = pretend.stub(session={}, method=method)

        with pytest.raises(SecurityError) as excinfo:
            handle_csrf(req, view)

        assert (excinfo.value.description
                == "No CSRF protection applied to view")

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_csrf_checks_csrf_unsafe(self, method, warehouse_app):
        view = lambda: Response()
        view._csrf = True

        req = pretend.stub(session={}, method=method)

        _verify_origin = pretend.call_recorder(lambda req: None)
        _verify_token = pretend.call_recorder(lambda req: None)

        with warehouse_app.test_request_context('/'):
            handle_csrf(
                req, view,
                _verify_origin=_verify_origin,
                _verify_token=_verify_token,
            )

            assert _verify_token.calls == [pretend.call(req)]
            assert _verify_token.calls == [pretend.call(req)]

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_csrf_exempts_csrf_unsafe(self, method):
        view = lambda: Response()
        view._csrf = False

        req = pretend.stub(_session={}, method=method)

        _verify_origin = pretend.call_recorder(lambda req: None)
        _verify_token = pretend.call_recorder(lambda req: None)

        handle_csrf(
            req, view,
            _verify_origin=_verify_origin,
            _verify_token=_verify_token,
        )

        assert _verify_token.calls == []
        assert _verify_token.calls == []


@pytest.mark.parametrize(("headers", "host_url", "valid", "error_msg"), [
    ({}, None, False, "Origin checking failed - no Origin or Referer."),
    (
        {"Origin": "null"},
        "https://example.com/",
        False,
        "Origin checking failed - null does not match https://example.com.",
    ),
    (
        {"Origin": "https://attacker.com"},
        "https://example.com/",
        False,
        "Origin checking failed - https://attacker.com does not match "
        "https://example.com.",
    ),
    (
        {"Referer": "https://attacker.com/wat/"},
        "https://example.com/",
        False,
        "Origin checking failed - https://attacker.com does not match "
        "https://example.com.",
    ),
    (
        {"Origin": "http://example.com"},
        "https://example.com/",
        False,
        "Origin checking failed - http://example.com does not match "
        "https://example.com.",
    ),
    (
        {"Referer": "http://example.com/wat/"},
        "https://example.com/",
        False,
        "Origin checking failed - http://example.com does not match "
        "https://example.com.",
    ),
    (
        {"Origin": "https://example.com:9000"},
        "https://example.com/",
        False,
        "Origin checking failed - https://example.com:9000 does not match "
        "https://example.com.",
    ),
    (
        {"Referer": "https://example.com:9000/wat/"},
        "https://example.com/",
        False,
        "Origin checking failed - https://example.com:9000 does not match "
        "https://example.com.",
    ),
    ({"Origin": "https://example.com"}, "https://example.com/", True, None),
    (
        {"Referer": "https://example.com/wat/"},
        "https://example.com/",
        True,
        None,
    ),
    (
        {
            "Origin": "https://example.com",
            "Referer": "https://attacker.com/wat/",
        },
        "https://example.com/",
        True,
        None,
    ),
])
def test_verify_csrf_origin(headers, host_url, valid, error_msg):
    req = pretend.stub(headers=headers, host_url=host_url)

    if valid:
        _verify_csrf_origin(req)
    else:
        with pytest.raises(SecurityError) as excinfo:
            _verify_csrf_origin(req)

        assert excinfo.value.description == error_msg


@pytest.mark.parametrize(
    ("token", "form", "headers", "valid", "error_msg"),
    [
        (None, {}, {}, False, "CSRF token not set."),
        ("1234", {}, {}, False, "CSRF token missing."),
        ("1234", {"csrf_token": "abcd"}, {}, False, "CSRF token incorrect."),
        ("1234", {}, {"X-CSRF-Token": "abcd"}, False, "CSRF token incorrect."),
        ("1234", {"csrf_token": "1234"}, {}, True, None),
        ("1234", {}, {"X-CSRF-Token": "1234"}, True, None),
    ],
)
def test_verify_csrf_token(
        token, form, headers, valid, error_msg, warehouse_app):
    req = pretend.stub(
        form=form,
        headers=headers,
        method="POST",
    )

    with warehouse_app.test_request_context():
        session['user.csrf'] = token

        if valid:
            _verify_csrf_token(req)
        else:
            with pytest.raises(SecurityError) as excinfo:
                _verify_csrf_token(req)

            assert excinfo.value.description == error_msg


@pytest.mark.parametrize("token", ["1234", None])
def test_ensure_csrf_token(token, warehouse_app):
    req = pretend.stub()

    with warehouse_app.test_request_context():
        session['user.csrf'] = token

        _ensure_csrf_token(req)

        if token:
            assert session["user.csrf"] == token
        else:
            assert session["user.csrf"]

        assert req._csrf


def test_csrf_protect():
    view = lambda: Response()
    view = csrf_protect(view)

    assert view._csrf
    assert "cookie" in view().vary.as_set()


def test_csrf_exempt():
    view = lambda: Response()
    view = csrf_exempt(view)

    assert not view._csrf


def test_csrf_cycle():
    session = {"user.csrf": "12345"}
    csrf_cycle(session)

    assert session["user.csrf"] != "12345"
