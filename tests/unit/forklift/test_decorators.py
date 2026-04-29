# SPDX-License-Identifier: Apache-2.0

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
            assert MultiDict({"real": "value"}) == request.POST
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
        req.metrics = pretend.stub(increment=lambda key, tags: None)

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
            user=pretend.stub(),
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
        req.metrics = pretend.stub(increment=lambda key, tags: None)

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
        req.metrics = pretend.stub(increment=lambda key, tags: None)

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
