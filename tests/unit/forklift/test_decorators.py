# SPDX-License-Identifier: Apache-2.0

import cgi

import pretend
import pytest

from pyramid.testing import DummyRequest
from webob.multidict import MultiDict

from warehouse.admin.flags import AdminFlagValue
from warehouse.forklift import decorators


class TestUploadMetrics:
    @pytest.mark.parametrize("filetype", [None, "bdist_foo"])
    def test_successful_view(self, filetype):
        m = pretend.stub(increment=pretend.call_recorder(lambda n, tags=None: None))
        request = pretend.stub(metrics=m, POST={"filetype": filetype})
        response = pretend.stub()

        @decorators.upload_metrics
        def wrapped(context, request):
            return response

        tags = {f"filetype:{filetype}"} if filetype else set()

        assert wrapped(pretend.stub(), request) is response
        assert request.metrics.increment.calls == [
            pretend.call("warehouse.upload.attempt", tags=tags),
            pretend.call("warehouse.upload.ok", tags=tags),
        ]

    @pytest.mark.parametrize("filetype", [None, "bdist_foo"])
    def test_forklift_error(self, filetype):
        m = pretend.stub(increment=pretend.call_recorder(lambda n, tags=None: None))
        request = pretend.stub(metrics=m, POST={"filetype": filetype})

        @decorators.upload_metrics
        def wrapped(context, request):
            raise decorators.InvalidTupleFieldError(field="foo")

        with pytest.raises(decorators.InvalidTupleFieldError):
            wrapped(pretend.stub(), request)

        tags = {f"filetype:{filetype}"} if filetype else set()

        assert request.metrics.increment.calls == [
            pretend.call("warehouse.upload.attempt", tags=tags),
            pretend.call(
                "warehouse.upload.failed", tags={"reason:field-is-tuple", "field:foo"}
            ),
        ]

    @pytest.mark.parametrize("filetype", [None, "bdist_foo"])
    def test_unknown_error(self, filetype):
        m = pretend.stub(increment=pretend.call_recorder(lambda n, tags=None: None))
        request = pretend.stub(metrics=m, POST={"filetype": filetype})

        class SomeError(Exception):
            pass

        @decorators.upload_metrics
        def wrapped(context, request):
            raise SomeError("blah")

        with pytest.raises(SomeError):
            wrapped(pretend.stub(), request)

        tags = {f"filetype:{filetype}"} if filetype else set()

        assert request.metrics.increment.calls == [
            pretend.call("warehouse.upload.attempt", tags=tags),
            pretend.call(
                "warehouse.upload.failed", tags={"reason:unknown-error"} | tags
            ),
        ]


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

        with pytest.raises(decorators.InvalidTupleFieldError) as excinfo:
            wrapped(pretend.stub(), req)

        assert excinfo.value.values == {"field": "keywords"}

    def test_fails_without_file(self):
        req = DummyRequest(post=MultiDict({}))

        @decorators.sanitize
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(decorators.NoFileUploadError):
            wrapped(pretend.stub(), req)

    @pytest.mark.parametrize("content_type", [None, "image/foobar"])
    def test_fails_invalid_content_type(self, content_type):
        req = DummyRequest(post=MultiDict({"content": pretend.stub(type=content_type)}))

        @decorators.sanitize
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(decorators.InvalidContentTypeError):
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
                decorators.ReadOnlyError,
            ),
            (
                AdminFlagValue.DISALLOW_NEW_UPLOAD,
                decorators.UploadsDisabledError,
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

        with pytest.raises(decorators.MissingIdentityError):
            wrapped(pretend.stub(), req)
