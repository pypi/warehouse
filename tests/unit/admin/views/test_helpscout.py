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

import base64
import hashlib
import hmac

import pretend

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

    def test_valid_auth_no_such_email(self, db_request):
        db_request.registry.settings["admin.helpscout.app_secret"] = "s3cr3t"
        db_request.body = b'{"customer": {"email": "wutang@loudrecords.com"}}'
        db_request.json_body = {"customer": {"email": "wutang@loudrecords.com"}}
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

    def test_valid_auth_email_found(self, db_request):
        email = EmailFactory.create(email="wutang@loudrecords.com")

        db_request.registry.settings["admin.helpscout.app_secret"] = "s3cr3t"
        db_request.body = b'{"customer": {"email": "wutang@loudrecords.com"}}'
        db_request.json_body = {"customer": {"email": "wutang@loudrecords.com"}}
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
