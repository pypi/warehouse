# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib
import hmac
import json

import pretend
import pytest

from warehouse.admin.views import helpscout as views

from ....common.db.accounts import EmailFactory


class TestHelpscoutApp:
    def test_no_secret(self, db_request):
        db_request.headers["X-HelpScout-Signature"] = base64.b64encode(b"bitsnbytes")
        result = views.helpscout(db_request)
        assert result == {"Error": "NotAuthorized"}

    def test_no_auth(self, db_request):
        db_request.registry.settings["admin.helpscout.app_secret"] = "s3cr3t"
        result = views.helpscout(db_request)
        assert result == {"Error": "NotAuthorized"}

    def test_invalid_auth(self, db_request):
        db_request.body = b""
        db_request.registry.settings["admin.helpscout.app_secret"] = "s3cr3t"
        db_request.headers["X-HelpScout-Signature"] = base64.b64encode(b"bitsnbytes")
        result = views.helpscout(db_request)
        assert result == {"Error": "NotAuthorized"}

    def test_valid_auth_no_payload(self, db_request):
        db_request.registry.settings["admin.helpscout.app_secret"] = "s3cr3t"
        db_request.body = b"{}"
        db_request.json_body = {}
        db_request.headers["X-HelpScout-Signature"] = base64.b64encode(
            hmac.digest(
                db_request.registry.settings["admin.helpscout.app_secret"].encode(),
                db_request.body,
                hashlib.sha1,
            )
        )
        result = views.helpscout(db_request)
        assert result == {
            "html": '<span class="badge pending">No PyPI user found</span>'
        }

    @pytest.mark.parametrize(
        "search_email",
        [
            "wutang@loudrecords.com",
            "wutang+pypi@loudrecords.com",
        ],
    )
    def test_valid_auth_no_such_email(self, db_request, search_email):
        EmailFactory.create(email="wutang@defjam.com")

        db_request.registry.settings["admin.helpscout.app_secret"] = "s3cr3t"
        db_request.json_body = {"customer": {"email": search_email}}
        db_request.body = json.dumps(db_request.json_body).encode()
        db_request.headers["X-HelpScout-Signature"] = base64.b64encode(
            hmac.digest(
                db_request.registry.settings["admin.helpscout.app_secret"].encode(),
                db_request.body,
                hashlib.sha1,
            )
        )
        result = views.helpscout(db_request)
        assert result == {
            "html": '<span class="badge pending">No PyPI user found</span>'
        }

    @pytest.mark.parametrize(
        ("search_email", "user_email"),
        [
            ("wutang@loudrecords.com", "wutang@loudrecords.com"),
            ("wutang+pypi@loudrecords.com", "wutang@loudrecords.com"),
            ("wutang@loudrecords.com", "wutang+pypi@loudrecords.com"),
        ],
    )
    def test_valid_auth_email_found(self, db_request, search_email, user_email):
        email = EmailFactory.create(email=user_email)

        db_request.registry.settings["admin.helpscout.app_secret"] = "s3cr3t"
        db_request.json_body = {"customer": {"email": f"{search_email}"}}
        db_request.body = json.dumps(db_request.json_body).encode()
        db_request.headers["X-HelpScout-Signature"] = base64.b64encode(
            hmac.digest(
                db_request.registry.settings["admin.helpscout.app_secret"].encode(),
                db_request.body,
                hashlib.sha1,
            )
        )
        db_request.route_url = pretend.call_recorder(
            lambda *a, **kw: "http://example.com"
        )
        result = views.helpscout(db_request)

        assert db_request.route_url.calls == [
            pretend.call("accounts.profile", username=email.user.username),
            pretend.call("admin.user.detail", username=email.user.username),
        ]
        assert result["html"][:26] == '<div class="c-sb-section">'
