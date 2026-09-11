# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib
import hmac
import json

import pretend
import pytest

from warehouse.admin.views import helpscout as views
from warehouse.organizations.models import OrganizationRoleType

from ....common.db.accounts import EmailFactory, UserFactory
from ....common.db.organizations import OrganizationFactory, OrganizationRoleFactory


def _sign_request(db_request):
    db_request.headers["X-HelpScout-Signature"] = base64.b64encode(
        hmac.digest(
            db_request.registry.settings["admin.helpscout.app_secret"].encode(),
            db_request.body,
            hashlib.sha1,
        )
    )


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
        _sign_request(db_request)
        result = views.helpscout(db_request)
        assert result == {
            "html": '<span class="badge pending">No PyPI user found</span>'
        }

    @pytest.mark.parametrize(
        "invalid_email",
        [
            "",
            "not-an-email",
            "missing@tld",
            "user+tag)invalid@domain.com",  # Invalid chars per RFC 5321
        ],
    )
    def test_valid_auth_invalid_email(self, db_request, invalid_email):
        db_request.registry.settings["admin.helpscout.app_secret"] = "s3cr3t"
        db_request.json_body = {"customer": {"email": invalid_email}}
        db_request.body = json.dumps(db_request.json_body).encode()
        _sign_request(db_request)
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
        _sign_request(db_request)
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
            # Subaddress with valid special characters
            ("wutang+pypi-test@loudrecords.com", "wutang@loudrecords.com"),
            ("wutang@loudrecords.com", "wutang+tag.test@loudrecords.com"),
        ],
    )
    def test_valid_auth_email_found(self, db_request, search_email, user_email):
        email = EmailFactory.create(email=user_email)

        db_request.registry.settings["admin.helpscout.app_secret"] = "s3cr3t"
        db_request.json_body = {"customer": {"email": f"{search_email}"}}
        db_request.body = json.dumps(db_request.json_body).encode()
        _sign_request(db_request)
        db_request.route_url = pretend.call_recorder(
            lambda *a, **kw: "http://example.com"
        )
        result = views.helpscout(db_request)

        assert db_request.route_url.calls == [
            pretend.call("accounts.profile", username=email.user.username),
            pretend.call("admin.user.detail", username=email.user.username),
        ]
        assert result["html"][:26] == '<div class="c-sb-section">'

    def test_valid_auth_renders_organizations(self, db_request, mocker):
        email = EmailFactory.create(email="rza@wutang.com")
        # excerise sorting
        member_org = OrganizationFactory.create(name="Zzz-wutang")
        member_role = OrganizationRoleFactory.create(
            organization=member_org,
            user=email.user,
            role_name=OrganizationRoleType.Member,
        )
        # Two owners, created out of order, to pin the owners-list sort.
        owner_role = OrganizationRoleFactory.create(
            organization=member_org,
            user=UserFactory.create(username="zeta-owner"),
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=member_org,
            user=UserFactory.create(username="alpha-owner"),
            role_name=OrganizationRoleType.Owner,
        )
        active_org = OrganizationFactory.create(name="aaa-wutang")
        OrganizationRoleFactory.create(
            organization=active_org,
            user=email.user,
            role_name=OrganizationRoleType.Owner,
        )
        inactive_org = OrganizationFactory.create(name="mmm-wutang", is_active=False)
        OrganizationRoleFactory.create(
            organization=inactive_org,
            user=email.user,
            role_name=OrganizationRoleType.BillingManager,
        )

        db_request.registry.settings["admin.helpscout.app_secret"] = "s3cr3t"
        db_request.json_body = {"customer": {"email": "rza@wutang.com"}}
        db_request.body = json.dumps(db_request.json_body).encode()
        _sign_request(db_request)
        route_url = mocker.patch.object(
            db_request, "route_url", return_value="http://example.com"
        )

        result = views.helpscout(db_request)

        html = result["html"]
        assert "Organizations (3)" in html
        assert '<span class="badge pending">Member</span>' in html
        assert '<span class="badge green">Owner</span>' in html
        assert '<span class="badge blue">Billing Manager</span>' in html
        assert owner_role.user.username in html
        assert html.index("alpha-owner") < html.index("zeta-owner")
        # Only the two organizations that have an Owner list one.
        assert html.count("Owners:") == 2

        # Organizations render sorted by name, case-insensitively.
        assert [
            org.name
            for org in sorted(
                (active_org, inactive_org, member_org), key=lambda o: html.index(o.name)
            )
        ] == ["aaa-wutang", "mmm-wutang", "Zzz-wutang"]

        # Inactive organizations have no public profile, so only name them.
        assert f'{inactive_org.name} <span class="badge red">Inactive</span>' in html
        assert (
            mocker.call("organizations.profile", organization=inactive_org.name)
            not in route_url.call_args_list
        )
        route_url.assert_any_call(
            "organizations.profile", organization=member_role.organization.name
        )
        route_url.assert_any_call("organizations.profile", organization=active_org.name)
        route_url.assert_any_call(
            "admin.organization.detail", organization_id=inactive_org.id
        )
        route_url.assert_any_call(
            "admin.organization.detail", organization_id=member_role.organization.id
        )
