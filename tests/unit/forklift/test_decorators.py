# SPDX-License-Identifier: Apache-2.0

import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden
from pyramid.testing import DummySecurityPolicy
from webob.compat import cgi_FieldStorage
from webob.multidict import MultiDict

from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.forklift import decorators

from ...common.db.accounts import UserFactory
from ...common.db.oidc import GitHubPublisherFactory


class TestSanitizeRequest:
    def test_removes_unknowns(self, pyramid_request, mocker):
        pyramid_request.method = "POST"
        pyramid_request.POST = MultiDict(
            {
                "foo": "UNKNOWN",
                "bar": "  UNKNOWN ",
                "real": "value",
            }
        )
        resp = mocker.sentinel.resp

        @decorators.sanitize
        def wrapped(context, request):
            assert MultiDict({"real": "value"}) == request.POST
            return resp

        assert wrapped(mocker.sentinel.context, pyramid_request) is resp

    def test_escapes_nul_characters(self, pyramid_request, mocker):
        pyramid_request.method = "POST"
        pyramid_request.POST = MultiDict({"summary": "I want to go to the \x00"})
        resp = mocker.sentinel.resp

        @decorators.sanitize
        def wrapped(context, request):
            assert "\x00" not in request.POST["summary"]
            return resp

        assert wrapped(mocker.sentinel.context, pyramid_request) is resp

    def test_fails_with_fieldstorage(self, pyramid_request, mocker):
        pyramid_request.method = "POST"
        # `list` of None is what WebOb leaves on a real parsed field; the
        # query-string parse this constructor runs would leave `[]`, which is
        # falsy and zero-length where a real field raises TypeError.
        field = cgi_FieldStorage(environ={"QUERY_STRING": ""})
        field.list = None
        pyramid_request.POST = MultiDict({"keywords": field})

        @decorators.sanitize
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(HTTPBadRequest) as excinfo:
            wrapped(mocker.sentinel.context, pyramid_request)

        resp = excinfo.value
        assert resp.status_code == 400
        assert resp.status == "400 keywords: Should not be a tuple."
        pyramid_request.metrics.increment.assert_called_once_with(
            "warehouse.upload.failed",
            tags=["reason:field-is-tuple", "field:keywords"],
        )


class TestEnsureUploadsAllowed:
    """The AdminFlag rows are seeded disabled by migration, so db_request's real
    Flags service answers False here."""

    def test_success_with_user(self, pyramid_config, db_request, mocker):
        pyramid_config.set_security_policy(
            DummySecurityPolicy(identity=UserFactory.build())
        )
        resp = mocker.sentinel.resp

        @decorators.ensure_uploads_allowed
        def wrapped(context, request):
            return resp

        assert wrapped(mocker.sentinel.context, db_request) is resp

    def test_success_with_nonuser(self, pyramid_config, db_request, mocker):
        pyramid_config.set_security_policy(
            DummySecurityPolicy(identity=GitHubPublisherFactory.build())
        )
        resp = mocker.sentinel.resp

        @decorators.ensure_uploads_allowed
        def wrapped(context, request):
            return resp

        assert wrapped(mocker.sentinel.context, db_request) is resp

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
    def test_disallowed_with_admin_flags(
        self, db_request, mocker, flag, error, help_url
    ):
        db_request.db.get(AdminFlag, flag.value).enabled = True
        db_request.help_url = lambda *a, **k: help_url

        @decorators.ensure_uploads_allowed
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(HTTPForbidden) as excinfo:
            wrapped(mocker.sentinel.context, db_request)

        resp = excinfo.value

        assert resp.status_code == 403
        assert resp.status == f"403 {error}"

    def test_fails_without_identity(self, pyramid_config, db_request, mocker):
        db_request.help_url = lambda *a, **k: "/path/to/help/"
        pyramid_config.set_security_policy(DummySecurityPolicy(identity=None))

        @decorators.ensure_uploads_allowed
        def wrapped(context, request):
            pytest.fail("wrapped view should not have been called")

        with pytest.raises(HTTPForbidden) as excinfo:
            wrapped(mocker.sentinel.context, db_request)

        resp = excinfo.value

        assert resp.status_code == 403
        assert resp.status == (
            "403 Invalid or non-existent authentication information. "
            "See /path/to/help/ for more information."
        )
