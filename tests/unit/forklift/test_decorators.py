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

import cgi

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden
from pyramid.testing import DummyRequest
from webob.multidict import MultiDict

from warehouse.admin.flags import AdminFlagValue
from warehouse.forklift import decorators


class TestSanitizeRequest:
    def test_removes_unknowns(self):
        req = DummyRequest(
            post=MultiDict(
                {
                    "foo": "UNKNOWN",
                    "bar": "  UNKNOWN ",
                    "real": "value",
                }
            )
        )
        resp = pretend.stub()

        @decorators.sanitize
        def wrapped(context, request):
            assert request.POST == MultiDict({"real": "value"})
            return resp

        assert wrapped(pretend.stub(), req) is resp

    def test_escapes_nul_characters(self):
        req = DummyRequest(post=MultiDict({"summary": "I want to go to the \x00"}))
        resp = pretend.stub()

        @decorators.sanitize
        def wrapped(context, request):
            assert "\x00" not in request.POST["summary"]
            return resp

        assert wrapped(pretend.stub(), req) is resp

    def test_fails_with_fieldstorage(self):
        req = DummyRequest(post=MultiDict({"keywords": cgi.FieldStorage()}))

        @decorators.sanitize
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(HTTPBadRequest) as excinfo:
            wrapped(pretend.stub(), req)

        resp = excinfo.value
        assert resp.status_code == 400
        assert resp.status == "400 keywords: Should not be a tuple."


class TestEnsureUploadsAllowed:

    def test_success_with_user(self):
        req = pretend.stub(
            flags=pretend.stub(enabled=lambda f: False),
            identity=pretend.stub(),
            user=pretend.stub(
                username="some-user",
                primary_email=pretend.stub(email="foo@example.com", verified=True),
            ),
        )
        resp = pretend.stub()

        @decorators.ensure_uploads_allowed
        def wrapped(context, request):
            return resp

        assert wrapped(pretend.stub(), req) is resp

    def test_success_with_nonuser(self):
        req = pretend.stub(
            flags=pretend.stub(enabled=lambda f: False),
            identity=pretend.stub(),
            user=None,
        )
        resp = pretend.stub()

        @decorators.ensure_uploads_allowed
        def wrapped(context, request):
            return resp

        assert wrapped(pretend.stub(), req) is resp

    @pytest.mark.parametrize(
        ("flag", "error", "help_url"),
        [
            (
                AdminFlagValue.READ_ONLY,
                "Read-only mode: Uploads are temporarily disabled.",
                "",
            ),
            (
                AdminFlagValue.DISALLOW_NEW_UPLOAD,
                (
                    "New uploads are temporarily disabled. "
                    "See /help/url/ for more information."
                ),
                "/help/url/",
            ),
        ],
    )
    def test_disallowed_with_admin_flags(self, flag, error, help_url):
        req = DummyRequest()
        req.flags = pretend.stub(enabled=lambda f: f is flag)
        req.help_url = lambda *a, **k: help_url

        @decorators.ensure_uploads_allowed
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(HTTPForbidden) as excinfo:
            wrapped(pretend.stub(), req)

        resp = excinfo.value

        assert resp.status_code == 403
        assert resp.status == f"403 {error}"

    def test_fails_without_identity(self):
        req = DummyRequest()
        req.flags = pretend.stub(enabled=lambda f: False)
        req.help_url = lambda *a, **k: "/path/to/help/"

        @decorators.ensure_uploads_allowed
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(HTTPForbidden) as excinfo:
            wrapped(pretend.stub(), req)

        resp = excinfo.value

        assert resp.status_code == 403
        assert resp.status == (
            "403 Invalid or non-existent authentication information. "
            "See /path/to/help/ for more information."
        )

    @pytest.mark.parametrize(
        ("email", "verified"),
        [
            ("foo@example.com", False),
            (None, None),
        ],
    )
    def test_requires_verified_email(self, email, verified):
        req = pretend.stub(
            flags=pretend.stub(enabled=lambda f: False),
            help_url=lambda *a, **k: "/path/to/help/",
            identity=pretend.stub(),
            user=pretend.stub(
                username="some-user",
                primary_email=(
                    pretend.stub(email=email, verified=verified)
                    if email is not None
                    else None
                ),
            ),
        )

        @decorators.ensure_uploads_allowed
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(HTTPForbidden) as excinfo:
            wrapped(pretend.stub(), req)

        resp = excinfo.value

        assert resp.status_code == 403
        assert resp.status == (
            "403 User 'some-user' does not have a verified primary email address. "
            "Please add a verified primary email before attempting to "
            "upload to PyPI. See /path/to/help/ for more information."
        )
