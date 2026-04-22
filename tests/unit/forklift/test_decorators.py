# SPDX-License-Identifier: Apache-2.0

import cgi

import pretend
import pytest

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
                    "content": cgi.FieldStorage(
                        headers={"content-type": "application/octet-stream"},
                    ),
                }
            )
        )
        resp = pretend.stub()

        @decorators.sanitize
        def wrapped(context, request):
            # Remove the content field as it doesn't compare correctly.
            del request.POST["content"]
            assert MultiDict({"real": "value"}) == request.POST
            return resp

        assert wrapped(pretend.stub(), req) is resp

    def test_escapes_nul_characters(self):
        req = DummyRequest(
            post=MultiDict(
                {
                    "summary": "I want to go to the \x00",
                    "content": cgi.FieldStorage(
                        headers={"content-type": "application/octet-stream"},
                    ),
                }
            )
        )
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

        with pytest.raises(decorators.InvalidTupleField) as excinfo:
            wrapped(pretend.stub(), req)

        assert excinfo.value.values == {"field": "keywords"}

    @pytest.mark.parametrize("content_type", [None, "image/foobar"])
    def test_fails_invalid_content_type(self, content_type):
        req = DummyRequest(post=MultiDict({"content": pretend.stub(type=content_type)}))

        @decorators.sanitize
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(decorators.InvalidContentType):
            wrapped(pretend.stub(), req)


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
        ("flag", "error_type"),
        [
            (
                AdminFlagValue.READ_ONLY,
                decorators.ReadOnlyEnabled,
            ),
            (
                AdminFlagValue.DISALLOW_NEW_UPLOAD,
                decorators.UploadsDisabled,
            ),
        ],
    )
    def test_disallowed_with_admin_flags(self, flag, error_type):
        req = DummyRequest()
        req.flags = pretend.stub(enabled=lambda f: f is flag)

        @decorators.ensure_uploads_allowed
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(error_type):
            wrapped(pretend.stub(), req)

    def test_fails_without_identity(self):
        req = DummyRequest()
        req.flags = pretend.stub(enabled=lambda f: False)

        @decorators.ensure_uploads_allowed
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(decorators.MissingIdentity):
            wrapped(pretend.stub(), req)
