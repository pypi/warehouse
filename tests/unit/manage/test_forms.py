# SPDX-License-Identifier: Apache-2.0

import uuid

from types import SimpleNamespace

import pytest
import wtforms

from webob.multidict import MultiDict

from warehouse.accounts.models import ProhibitedEmailDomain
from warehouse.accounts.services import NullPasswordBreachedService
from warehouse.manage import forms
from warehouse.organizations.models import OrganizationApplicationStatus
from warehouse.utils import otp

from ...common.db.accounts import (
    EmailFactory,
    OAuthAccountAssociationFactory,
    UserFactory,
    WebAuthnFactory,
)
from ...common.db.macaroons import MacaroonFactory
from ...common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
    TeamFactory,
)
from ...common.db.packaging import ProjectFactory

VALID_APPLICATION = {
    "name": "my_organization_name",
    "display_name": "My Organization",
    "link_url": "https://example.com/",
    "description": "An organization",
    "orgtype": "Community",
    "membership_size": "1",
    "usage": "We plan to publish a handful of packages under one organization.",
}


def _stub_mx_ptr_resolution(monkeypatch, ptr_host):
    """
    Stub ``dns.resolver`` so the MX-record-to-PTR lookup in email validation
    runs deterministically without live network queries.

    Without this, coverage of the PTR-resolution branch in
    ``warehouse/accounts/forms.py`` depends on CI DNS resolving real MX hosts,
    which is non-deterministic and produces flaky coverage failures.
    """
    monkeypatch.setattr(
        "dns.resolver.resolve",
        lambda *a, **kw: [SimpleNamespace(address="192.0.2.1")],
    )
    monkeypatch.setattr(
        "dns.resolver.resolve_address",
        lambda *a, **kw: [
            SimpleNamespace(target=SimpleNamespace(to_text=lambda: ptr_host))
        ],
    )


class TestCreateRoleForm:
    def test_validate(self, user_service):
        UserFactory.create(username="valid_username")
        form = forms.CreateRoleForm(
            formdata=MultiDict({"role_name": "Owner", "username": "valid_username"}),
            user_service=user_service,
        )

        assert form.user_service is user_service
        assert form.validate(), str(form.errors)

    def test_validate_username_with_no_user(self, user_service, mocker):
        find_userid = mocker.spy(user_service, "find_userid")
        form = forms.CreateRoleForm(user_service=user_service)
        form.username.data = "my_username"

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_username(form.username)

        find_userid.assert_called_once_with("my_username")

    def test_validate_username_with_user(self, user_service, mocker):
        UserFactory.create(username="my_username")
        find_userid = mocker.spy(user_service, "find_userid")
        form = forms.CreateRoleForm(user_service=user_service)
        form.username.data = "my_username"

        form.validate_username(form.username)

        find_userid.assert_called_once_with("my_username")

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("", "Select role"),
            ("invalid", "Not a valid choice."),
            (None, "Select role"),
        ],
    )
    def test_validate_role_name_fails(self, user_service, value, expected):
        UserFactory.create(username="valid_username")
        form = forms.CreateRoleForm(
            MultiDict({"role_name": value, "username": "valid_username"}),
            user_service=user_service,
        )

        assert not form.validate()
        assert form.role_name.errors == [expected]


class TestCreateInternalRoleForm:
    @pytest.mark.parametrize(
        ("is_team", "team_name", "team_choices", "username", "user_choices", "errors"),
        [
            # Team validators
            ("true", "", [], "", [], {"team_name": ["This field is required."]}),
            ("true", "team", [], "", [], {"team_name": ["Not a valid choice."]}),
            ("true", "team", ["team"], "", [], {}),
            # User validators
            ("false", "", [], "", [], {"username": ["This field is required."]}),
            ("false", "", [], "foo", [], {"username": ["Not a valid choice."]}),
            ("false", "", [], "foo", ["foo"], {}),
        ],
    )
    def test_validate(
        self,
        pyramid_request,
        user_service,
        is_team,
        team_name,
        team_choices,
        username,
        user_choices,
        errors,
    ):
        pyramid_request.POST = MultiDict(
            {
                "is_team": is_team,
                "team_name": team_name,
                "username": username,
                # Required fields with no effect on validation
                "role_name": "Maintainer",
                "team_project_role_name": "Maintainer",
            }
        )

        form = forms.CreateInternalRoleForm(
            pyramid_request.POST,
            team_choices=team_choices,
            user_choices=user_choices,
            user_service=user_service,
        )

        assert form.user_service is user_service
        assert not form.validate() if errors else form.validate(), str(form.errors)
        assert form.errors == errors


class TestSaveAccountForm:
    def test_validate(self, user_service):
        email = EmailFactory.create(verified=True, public=False)
        form = forms.SaveAccountForm(
            name="some name",
            public_email=email.email,
            user_service=user_service,
            user_id=email.user.id,
        )

        assert form.user_id is email.user.id
        assert form.user_service is user_service
        assert form.validate(), str(form.errors)

    def test_public_email_unverified(self, user_service):
        email = EmailFactory.create(verified=False, public=False)
        form = forms.SaveAccountForm(
            name="some name",
            public_email=email.email,
            user_service=user_service,
            user_id=email.user.id,
        )
        assert not form.validate()
        assert "is not a verified email for" in form.public_email.errors.pop()

    def test_name_too_long(self, pyramid_config, user_service):
        email = EmailFactory.create(verified=True, public=False)
        form = forms.SaveAccountForm(
            name="x" * 101,
            public_email=email.email,
            user_service=user_service,
            user_id=email.user.id,
        )

        assert not form.validate()
        assert (
            str(form.name.errors.pop())
            == "The name is too long. Choose a name with 100 characters or less."
        )


class TestAddEmailForm:
    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_validate(self, db_request, user_service):
        user = UserFactory.create()
        form = forms.AddEmailForm(
            request=db_request,
            formdata=MultiDict({"email": "foo@bar.com"}),
            user_id=user.id,
            user_service=user_service,
        )

        assert form.user_id is user.id
        assert form.user_service is user_service
        assert form.validate(), str(form.errors)

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_email_exists_error(self, db_request, user_service):
        email = EmailFactory.create(email="foo@bar.com")
        form = forms.AddEmailForm(
            request=db_request,
            formdata=MultiDict({"email": "foo@bar.com"}),
            user_id=email.user.id,
            user_service=user_service,
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "This email address is already being used by this account. "
            "Use a different email."
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_email_exists_other_account_error(self, db_request, user_service):
        EmailFactory.create(email="foo@bar.com")
        form = forms.AddEmailForm(
            request=db_request,
            formdata=MultiDict({"email": "foo@bar.com"}),
            user_id=UserFactory.create().id,
            user_service=user_service,
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "This email address is already being used by another account. "
            "Use a different email."
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_prohibited_email_error(self, db_request, user_service):
        form = forms.AddEmailForm(
            request=db_request,
            formdata=MultiDict({"email": "foo@bearsarefuzzy.com"}),
            user_service=user_service,
            user_id=UserFactory.create().id,
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "You can't use an email address from this domain. "
            "Use a different email."
        )

    @pytest.mark.parametrize(
        ("email_address", "mx_record_domain", "mx_ptr_host", "prohibited_domain"),
        [
            # Prohibited via the MX record's own domain
            ("foo@wutang.net", "in.mail.net", "ptr.example.org", "mail.net"),
            ("foo@wutang.net", "in.mail.net", "ptr.example.org", "in.mail.net"),
            (
                "foo@outlook.com",
                "outlook-com.mail.protection.outlook.com",
                "ptr.example.org",
                "outlook.com",
            ),
            # Prohibited via the domain the MX host's IP resolves back to (PTR)
            (
                "foo@wutang.net",
                "in.someisp.com",
                "mx1.prohibited-ptr.net",
                "prohibited-ptr.net",
            ),
        ],
    )
    def test_prohibited_mx_domain_error(
        self,
        monkeypatch,
        db_request,
        user_service,
        email_address,
        mx_record_domain,
        mx_ptr_host,
        prohibited_domain,
    ):
        """
        Similar to `test_prohibited_email_error()`, checking the MX domain.

        Both the MX record's own domain and the domain its IP points back to
        (via a PTR lookup) are checked against the prohibited list. DNS
        resolution is stubbed so coverage of the PTR-resolution branch does not
        depend on live network lookups.
        """
        mock_deliverability_info = {"mx": [(10, mx_record_domain)]}

        def mock_function(*args, **kwargs):
            return mock_deliverability_info

        monkeypatch.setattr(
            "email_validator.deliverability.validate_email_deliverability",
            mock_function,
        )
        _stub_mx_ptr_resolution(monkeypatch, mx_ptr_host)

        prohibited_mx_domain = ProhibitedEmailDomain(
            domain=prohibited_domain,
            is_mx_record=True,
        )
        db_request.db.add(prohibited_mx_domain)

        form = forms.AddEmailForm(
            request=db_request,
            formdata=MultiDict({"email": email_address}),
            user_service=user_service,
            user_id=UserFactory.create().id,
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "You can't use an email address from this domain. "
            "Use a different email."
        )

    @pytest.mark.parametrize(
        ("email_address", "mx_record_domain", "prohibited_domain"),
        [
            (
                "foo@microsoft.com",
                "microsoft-com.mail.protection.outlook.com",
                "outlook.com",
            ),
        ],
    )
    def test_prohibited_mx_domain_passes(
        self,
        monkeypatch,
        db_request,
        user_service,
        email_address,
        mx_record_domain,
        prohibited_domain,
    ):
        """
        Similar to `test_prohibited_email_error()`, allowing if:
          - the `registered_domain` part of the email address is **not** prohibited
          - the `registered_domain` part of the MX record is prohibited

        This is to allow for cases where the email address that shares MX records with a
        prohibited domain is not itself prohibited.
        """
        mock_deliverability_info = {"mx": [(10, mx_record_domain)]}

        def mock_function(*args, **kwargs):
            return mock_deliverability_info

        monkeypatch.setattr(
            "email_validator.deliverability.validate_email_deliverability",
            mock_function,
        )
        _stub_mx_ptr_resolution(monkeypatch, "ptr.example.org")

        prohibited_mx_domain = ProhibitedEmailDomain(
            domain=prohibited_domain,
            is_mx_record=False,
        )
        db_request.db.add(prohibited_mx_domain)

        form = forms.AddEmailForm(
            request=db_request,
            formdata=MultiDict({"email": email_address}),
            user_service=user_service,
            user_id=UserFactory.create().id,
        )

        assert form.validate()

    def test_email_too_long_error(self, pyramid_request, user_service):
        form = forms.AddEmailForm(
            request=pyramid_request,
            formdata=MultiDict({"email": f"{'x' * 300}@bar.com"}),
            user_service=user_service,
            user_id=uuid.uuid4(),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop()) == "The email address isn't valid. Try again."
        )


class TestChangeUnverifiedPrimaryEmailForm:
    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_validate(self, db_request, user_service):
        user = UserFactory.create()
        form = forms.ChangeUnverifiedPrimaryEmailForm(
            request=db_request,
            formdata=MultiDict({"email": "foo@bar.com"}),
            user_id=user.id,
            user_service=user_service,
        )

        assert form.user_id is user.id
        assert form.user_service is user_service
        assert form.validate(), str(form.errors)

    def test_params(self):
        assert forms.ChangeUnverifiedPrimaryEmailForm.__params__ == [
            "change_unverified_primary_email"
        ]


class TestChangePasswordForm:
    def test_validate(self, db_request, user_service):
        UserFactory.create(username="username", clear_pwd="password")
        breach_service = NullPasswordBreachedService()

        form = forms.ChangePasswordForm(
            formdata=MultiDict(
                {
                    "password": "password",
                    "new_password": "mysupersecurepassword1!",
                    "password_confirm": "mysupersecurepassword1!",
                    "username": "username",
                    "email": "foo@bar.net",
                }
            ),
            request=db_request,
            user_service=user_service,
            breach_service=breach_service,
        )

        assert form.request is db_request
        assert form.user_service is user_service
        assert form._breach_service is breach_service
        assert form.validate(), str(form.errors)


class TestDeleteTOTPForm:
    """
    Covers ConfirmPasswordForm
    """

    def test_validate_confirm_password(self, db_request, user_service):
        UserFactory.create(username="username", clear_pwd="password")
        form = forms.DeleteTOTPForm(
            formdata=MultiDict({"username": "username", "password": "password"}),
            request=db_request,
            user_service=user_service,
        )

        assert form.request is db_request
        assert form.user_service is user_service
        assert form.validate(), str(form.errors)


class TestProvisionTOTPForm:
    def test_validate(self, mocker):
        verify_totp = mocker.patch.object(
            otp, "verify_totp", autospec=True, return_value=True
        )

        totp_secret = mocker.sentinel.totp_secret
        form = forms.ProvisionTOTPForm(
            formdata=MultiDict({"totp_value": "000000"}), totp_secret=totp_secret
        )

        assert form.totp_secret is totp_secret
        assert form.validate(), str(form.errors)
        verify_totp.assert_called_once_with(totp_secret, b"000000")

    @pytest.mark.parametrize(
        ("exception", "expected_error", "expected_failure"),
        [
            (otp.InvalidTOTPError, "Invalid TOTP code. Try again?", "invalid"),
            (
                otp.OutOfSyncTOTPError,
                "Invalid TOTP code. Your device time may be out of sync.",
                "out_of_sync",
            ),
        ],
    )
    def test_verify_totp_invalid(
        self, mocker, exception, expected_error, expected_failure
    ):
        mocker.patch.object(otp, "verify_totp", autospec=True, side_effect=exception)

        form = forms.ProvisionTOTPForm(
            formdata=MultiDict({"totp_value": "123456"}),
            totp_secret=mocker.sentinel.totp_secret,
        )
        assert not form.validate()
        assert form.totp_value.errors.pop() == expected_error
        assert form.totp_failure == expected_failure

    def test_verify_totp_malformed(self):
        form = forms.ProvisionTOTPForm(
            formdata=MultiDict({"totp_value": "12345"}),
            totp_secret=otp.generate_totp_secret(),
        )
        assert not form.validate()
        assert form.totp_failure == "malformed"


class TestDeleteWebAuthnForm:
    def test_validate(self, user_service):
        webauthn = WebAuthnFactory.create(label="fake label")
        form = forms.DeleteWebAuthnForm(
            formdata=MultiDict({"label": "fake label"}),
            user_service=user_service,
            user_id=webauthn.user.id,
        )

        assert form.user_service is user_service
        assert form.user_id is webauthn.user.id
        assert form.validate(), str(form.errors)
        assert form.webauthn == webauthn

    def test_validate_label_missing(self, user_service):
        form = forms.DeleteWebAuthnForm(
            user_service=user_service, user_id=UserFactory.create().id
        )

        assert not form.validate()
        assert form.label.errors.pop() == "Specify a device name"

    def test_validate_label_not_in_use(self, user_service):
        webauthn = WebAuthnFactory.create(label="another label")
        form = forms.DeleteWebAuthnForm(
            formdata=MultiDict({"label": "fake label"}),
            user_service=user_service,
            user_id=webauthn.user.id,
        )

        assert not form.validate()
        assert form.label.errors.pop() == "No WebAuthn key with given label"


class TestProvisionWebAuthnForm:
    @pytest.fixture
    def verify_webauthn_credential(self, user_service, mocker):
        return mocker.patch.object(
            user_service, "verify_webauthn_credential", autospec=True
        )

    @pytest.fixture
    def make_form(self, user_service, mocker):
        """
        Build a ProvisionWebAuthnForm with opaque challenge/rp_id/origin values.
        """

        def _make(formdata, user_id=None):
            return forms.ProvisionWebAuthnForm(
                formdata=MultiDict(formdata),
                user_service=user_service,
                user_id=user_id or UserFactory.create().id,
                challenge=mocker.sentinel.challenge,
                rp_id=mocker.sentinel.rp_id,
                origin=mocker.sentinel.origin,
            )

        return _make

    def test_validate(self, mocker, user_service, verify_webauthn_credential):
        user_id = UserFactory.create().id
        challenge = mocker.sentinel.challenge
        rp_id = mocker.sentinel.rp_id
        origin = mocker.sentinel.origin
        form = forms.ProvisionWebAuthnForm(
            formdata=MultiDict({"label": "label", "credential": "{}"}),
            user_service=user_service,
            user_id=user_id,
            challenge=challenge,
            rp_id=rp_id,
            origin=origin,
        )

        assert form.user_service is user_service
        assert form.user_id is user_id
        assert form.challenge is challenge
        assert form.rp_id is rp_id
        assert form.origin is origin
        assert form.validate(), str(form.errors)
        verify_webauthn_credential.assert_called_once_with(
            b"{}", challenge=challenge, rp_id=rp_id, origin=origin
        )

    def test_verify_assertion_invalid_json(self, make_form):
        form = make_form({"credential": "invalid json", "label": "fake label"})

        assert not form.validate()
        assert (
            form.credential.errors.pop() == "Invalid WebAuthn credential: Bad payload"
        )

    def test_verify_credential_invalid(self, user_service):
        user = UserFactory.create()
        form = forms.ProvisionWebAuthnForm(
            formdata=MultiDict(
                {
                    "credential": (
                        '{"id": "foo", "rawId": "foo", "response": '
                        '{"attestationObject": "foo", "clientDataJSON": "bar"}, '
                        '"type": "public-key"}'
                    ),
                    "label": "fake label",
                }
            ),
            user_service=user_service,
            user_id=user.id,
            challenge=b"not_a_real_challenge",
            rp_id="fake_rp_id",
            origin="fake_origin",
        )

        assert not form.validate()

    @pytest.mark.usefixtures("verify_webauthn_credential")
    def test_verify_label_missing(self, make_form):
        form = make_form({"credential": "{}"})

        assert not form.validate()
        assert form.label.errors.pop() == "Specify a label"

    @pytest.mark.usefixtures("verify_webauthn_credential")
    def test_verify_label_already_in_use(self, make_form):
        webauthn = WebAuthnFactory.create(label="fake label")
        form = make_form(
            {"credential": "{}", "label": "fake label"}, user_id=webauthn.user.id
        )

        assert not form.validate()
        assert form.label.errors.pop() == "Label 'fake label' already in use"

    def test_creates_validated_credential(self, make_form, verify_webauthn_credential):
        form = make_form({"credential": "{}", "label": "fake label"})

        assert form.validate(), str(form.errors)
        assert form.validated_credential is verify_webauthn_credential.return_value


class TestCreateMacaroonForm:
    @pytest.fixture
    def make_form(self, macaroon_service):
        """
        Build a CreateMacaroonForm for a fresh user.
        """

        def _make(formdata, project_names=(), user_id=None):
            return forms.CreateMacaroonForm(
                formdata=MultiDict(formdata),
                user_id=user_id or UserFactory.create().id,
                macaroon_service=macaroon_service,
                project_names=list(project_names),
            )

        return _make

    @pytest.mark.parametrize("selected_project", [None, "foo"])
    def test_creation(self, macaroon_service, selected_project):
        user_id = UserFactory.create().id
        project_names = ["foo"]
        form = forms.CreateMacaroonForm(
            formdata=MultiDict(
                {"description": "description", "token_scope": "token:user"}
            ),
            user_id=user_id,
            macaroon_service=macaroon_service,
            project_names=project_names,
            selected_project=selected_project,
        )

        assert form.user_id is user_id
        assert form.macaroon_service is macaroon_service
        assert form.project_names is project_names
        assert form.validate()

    def test_validate_description_missing(self, make_form):
        form = make_form({"token_scope": "scope:user"})

        assert not form.validate()
        assert form.description.errors.pop() == "Specify a token name"

    def test_validate_description_in_use(self, make_form):
        user = UserFactory.create()
        MacaroonFactory.create(user_id=user.id, description="dummy")
        form = make_form(
            {"description": "dummy", "token_scope": "scope:user"}, user_id=user.id
        )

        assert not form.validate()
        assert form.description.errors.pop() == "API token name already in use"

    @pytest.mark.parametrize(
        "formdata",
        [
            {"description": "dummy"},
            {"description": "dummy", "token_scope": "scope:unspecified"},
        ],
    )
    def test_validate_token_scope_missing(self, make_form, formdata):
        form = make_form(formdata)

        assert not form.validate()
        assert form.token_scope.errors.pop() == "Specify the token scope"

    @pytest.mark.parametrize(
        ("scope"), ["not a real scope", "scope:project", "scope:foo:bar"]
    )
    def test_validate_token_scope_invalid_format(self, make_form, scope):
        form = make_form({"description": "dummy", "token_scope": scope})

        assert not form.validate()
        assert form.token_scope.errors.pop() == f"Unknown token scope: {scope}"

    def test_validate_token_scope_invalid_project(self, make_form):
        form = make_form(
            {"description": "dummy", "token_scope": "scope:project:foo"},
            project_names=["bar"],
        )

        assert not form.validate()
        assert form.token_scope.errors.pop() == "Unknown or invalid project name: foo"

    def test_validate_token_scope_valid_user(self, make_form):
        form = make_form({"description": "dummy", "token_scope": "scope:user"})

        assert form.validate()

    def test_validate_token_scope_valid_project(self, make_form):
        form = make_form(
            {"description": "dummy", "token_scope": "scope:project:foo"},
            project_names=["foo"],
        )

        assert form.validate()


class TestDeleteMacaroonForm:
    @pytest.fixture
    def user(self):
        return UserFactory.create(username="username", clear_pwd="password")

    def test_validate(self, db_request, macaroon_service, user_service, user):
        macaroon = MacaroonFactory.create(user_id=user.id)
        form = forms.DeleteMacaroonForm(
            formdata=MultiDict(
                {
                    "password": "password",
                    "username": "username",
                    "macaroon_id": str(macaroon.id),
                }
            ),
            request=db_request,
            macaroon_service=macaroon_service,
            user_service=user_service,
        )

        assert form.request is db_request
        assert form.macaroon_service is macaroon_service
        assert form.user_service is user_service
        assert form.validate(), str(form.errors)

    def test_validate_macaroon_id_invalid(
        self, db_request, macaroon_service, user_service, user
    ):
        form = forms.DeleteMacaroonForm(
            formdata=MultiDict(
                {"macaroon_id": str(uuid.uuid4()), "password": "password"}
            ),
            request=db_request,
            macaroon_service=macaroon_service,
            user_service=user_service,
            username="username",
        )

        assert not form.validate()
        assert form.macaroon_id.errors.pop() == "No such macaroon"


class TestCreateOrganizationApplicationForm:
    def test_creation(self, organization_service):
        user = UserFactory.create()
        form = forms.CreateOrganizationApplicationForm(
            organization_service=organization_service,
            user=user,
        )

        assert form.organization_service is organization_service
        assert form.user is user

    def test_validate_name_with_no_organization(self, organization_service, mocker):
        get_applications = mocker.spy(
            organization_service, "get_organization_applications_by_name"
        )
        find_organizationid = mocker.spy(organization_service, "find_organizationid")
        user = UserFactory.create()
        form = forms.CreateOrganizationApplicationForm(
            organization_service=organization_service,
            user=user,
        )
        form.name.data = "my_organization_name"

        form.validate_name(form.name)

        get_applications.assert_called_once_with(
            "my_organization_name", submitted_by=user, undecided=True
        )
        find_organizationid.assert_called_once_with("my_organization_name")

    def test_validate_name_with_existing_application(
        self, organization_service, mocker
    ):
        user = UserFactory.create()
        OrganizationApplicationFactory.create(
            name="my_organization_name", submitted_by=user
        )
        get_applications = mocker.spy(
            organization_service, "get_organization_applications_by_name"
        )
        find_organizationid = mocker.spy(organization_service, "find_organizationid")
        form = forms.CreateOrganizationApplicationForm(
            organization_service=organization_service,
            user=user,
        )
        form.name.data = "my_organization_name"

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_name(form.name)

        get_applications.assert_called_once_with(
            "my_organization_name", submitted_by=user, undecided=True
        )
        find_organizationid.assert_called_once_with("my_organization_name")

    @pytest.mark.parametrize(
        "status",
        [
            OrganizationApplicationStatus.Approved,
            OrganizationApplicationStatus.Declined,
        ],
    )
    def test_validate_max_applications_ignores_decided(
        self, organization_service, status
    ):
        user = UserFactory.create()
        OrganizationApplicationFactory.create_batch(3, submitted_by=user, status=status)
        form = forms.CreateOrganizationApplicationForm(
            MultiDict(VALID_APPLICATION),
            organization_service=organization_service,
            user=user,
            max_applications=3,
        )

        assert form.validate(), str(form.errors)
        assert form.form_errors == []

    def test_validate_max_applications_reached(
        self, pyramid_config, organization_service
    ):
        user = UserFactory.create()
        OrganizationApplicationFactory.create_batch(
            3, submitted_by=user, status=OrganizationApplicationStatus.Deferred
        )
        form = forms.CreateOrganizationApplicationForm(
            MultiDict(VALID_APPLICATION),
            organization_service=organization_service,
            user=user,
            max_applications=3,
        )

        assert not form.validate()
        assert [str(error) for error in form.form_errors] == [
            (
                "You have already submitted the maximum number of "
                "Organization requests (3)."
            )
        ]

    def test_validate_name_with_organization(self, organization_service, mocker):
        OrganizationFactory.create(name="my_organization_name")
        find_organizationid = mocker.spy(organization_service, "find_organizationid")
        form = forms.CreateOrganizationApplicationForm(
            organization_service=organization_service,
            user=UserFactory.create(),
        )
        form.name.data = "my_organization_name"

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_name(form.name)

        find_organizationid.assert_called_once_with("my_organization_name")

    def test_validate_name_with_null_bytes(self, organization_service, mocker):
        find_organizationid = mocker.spy(organization_service, "find_organizationid")
        form = forms.CreateOrganizationApplicationForm(
            MultiDict({"name": "test\x00name"}),
            organization_service=organization_service,
            user=UserFactory.create(),
        )
        assert not form.validate()
        assert "Null bytes are not allowed." in form.name.errors
        find_organizationid.assert_not_called()


class TestSaveOrganizationNameForm:
    def test_save(self, pyramid_request, organization_service, mocker):
        find_organizationid = mocker.spy(organization_service, "find_organizationid")
        pyramid_request.POST = MultiDict({"name": "my_org_name"})
        form = forms.SaveOrganizationNameForm(
            pyramid_request.POST,
            organization_service=organization_service,
            user=UserFactory.create(),
        )
        form.validate()
        find_organizationid.assert_called_once_with("my_org_name")


class TestAddOrganizationProjectForm:
    @pytest.mark.parametrize(
        ("add_existing_project", "existing_project_name", "new_project_name", "errors"),
        [
            # Validate existing project name.
            ("true", "foo", "", {}),
            # Validate existing project name missing.
            ("true", "", "", {"existing_project_name": ["Select project"]}),
            # Validate new project name.
            ("false", "", "bar", {}),
            # Validate new project name missing.
            ("false", "", "", {"new_project_name": ["Specify project name"]}),
            # Validate new project name invalid character.
            (
                "false",
                "",
                "@",
                {
                    "new_project_name": [
                        (
                            "Start and end with a letter or numeral containing "
                            "only ASCII numeric and '.', '_' and '-'."
                        )
                    ]
                },
            ),
            # Validate new project name already used.
            (
                "false",
                "",
                "foo",
                {
                    "new_project_name": [
                        (
                            "This project name has already been used. "
                            "Choose a different project name."
                        )
                    ]
                },
            ),
        ],
    )
    def test_validate(
        self,
        pyramid_request,
        add_existing_project,
        existing_project_name,
        new_project_name,
        errors,
    ):
        pyramid_request.POST = MultiDict(
            {
                "add_existing_project": add_existing_project,
                "existing_project_name": existing_project_name,
                "new_project_name": new_project_name,
            }
        )
        project_choices = {"foo"}
        project_factory = {"foo": ProjectFactory.create(name="foo")}

        form = forms.AddOrganizationProjectForm(
            pyramid_request.POST,
            project_choices=project_choices,
            project_factory=project_factory,
        )

        assert form.existing_project_name.choices == [
            ("", "Select project"),
            ("foo", "foo"),
        ]
        assert not form.validate() if errors else form.validate(), str(form.errors)
        assert form.errors == errors


class TestTransferOrganizationProjectForm:
    def test_validate(self, pyramid_request):
        organization = OrganizationFactory()
        pyramid_request.POST = MultiDict({"organization": organization.id})

        form = forms.TransferOrganizationProjectForm(
            pyramid_request.POST, organization_choices=[organization]
        )

        assert form.validate()

    def test_rejects_inactive_company(self, pyramid_request):
        organization = OrganizationFactory(orgtype="Company")
        pyramid_request.POST = MultiDict({"organization": organization.id})

        form = forms.TransferOrganizationProjectForm(
            pyramid_request.POST, organization_choices=[organization]
        )

        assert not form.validate()
        assert form.errors == {
            "organization": [
                "Cannot transfer to Company Organization with inactive billing"
            ]
        }


class TestCreateOrganizationRoleForm:
    def test_validate(self, organization_service, user_service):
        UserFactory.create(username="user")

        form = forms.CreateOrganizationRoleForm(
            MultiDict({"username": "user", "role_name": "Owner"}),
            orgtype="Company",
            organization_service=organization_service,
            user_service=user_service,
        )

        assert form.organization_service is organization_service
        assert form.user_service is user_service
        assert form.validate(), str(form.errors)


class TestCreateTeamRoleForm:
    @pytest.mark.parametrize(
        ("username", "user_choices", "errors"),
        [
            ("", [], {"username": ["This field is required."]}),
            ("", ["user"], {"username": ["This field is required."]}),
            ("user", ["user"], {}),
        ],
    )
    def test_validate(self, pyramid_request, username, user_choices, errors):
        pyramid_request.POST = MultiDict({"username": username})

        form = forms.CreateTeamRoleForm(pyramid_request.POST, user_choices=user_choices)

        assert not form.validate() if errors else form.validate(), str(form.errors)
        assert form.errors == errors


class TestCreateTeamForm:
    """
    Covers SaveTeamForm.
    """

    @pytest.mark.parametrize(
        ("name", "errors"),
        [
            ("", ["name"]),
            (" team ", ["name"]),
            (".team", ["name"]),
            ("team-", ["name"]),
            ("team", []),
        ],
    )
    def test_validate(self, pyramid_request, organization_service, name, errors):
        pyramid_request.POST = MultiDict({"name": name})
        # Renaming a team to its own name must not collide with itself.
        team = TeamFactory.create(name="team")
        team_id = team.id

        form = forms.CreateTeamForm(
            pyramid_request.POST,
            team_id=team_id,
            organization_id=team.organization.id,
            organization_service=organization_service,
        )

        assert form.team_id is team_id
        assert form.organization_service is organization_service
        assert not form.validate() if errors else form.validate(), str(form.errors)
        # NOTE(jleightcap): testing with Regexp validators returns raw LazyString
        # objects in the error dict's values. Just assert on keys.
        assert list(form.errors.keys()) == errors


class TestDeleteAccountAssociationForm:
    def test_validate_association_id_valid(self, user_service, mocker):
        user = UserFactory.create()
        association = OAuthAccountAssociationFactory.create(user=user)
        get_account_association = mocker.spy(user_service, "get_account_association")

        form = forms.DeleteAccountAssociationForm(
            MultiDict({"association_id": str(association.id)}),
            user_service=user_service,
            user_id=str(user.id),
        )

        assert form.validate()
        assert form.association == association
        get_account_association.assert_called_once_with(str(association.id))

    def test_validate_association_id_missing(self, user_service):
        form = forms.DeleteAccountAssociationForm(
            MultiDict({}), user_service=user_service, user_id="some-user-id"
        )

        assert not form.validate()
        assert "association_id" in form.errors
        assert form.errors["association_id"][0] == "Specify an association ID"

    def test_validate_association_id_invalid_uuid(self, user_service, mocker):
        get_account_association = mocker.spy(user_service, "get_account_association")
        form = forms.DeleteAccountAssociationForm(
            MultiDict({"association_id": "not-a-uuid"}),
            user_service=user_service,
            user_id="some-user-id",
        )

        assert not form.validate()
        assert "association_id" in form.errors
        assert form.errors["association_id"] == ["Association must be specified by ID"]
        get_account_association.assert_not_called()

    def test_validate_association_id_not_found(self, user_service, mocker):
        get_account_association = mocker.spy(user_service, "get_account_association")

        association_id = "12345678-1234-1234-1234-123456789012"
        form = forms.DeleteAccountAssociationForm(
            MultiDict({"association_id": association_id}),
            user_service=user_service,
            user_id="some-user-id",
        )

        assert not form.validate()
        assert "association_id" in form.errors
        assert (
            form.errors["association_id"][0] == "No account association with given ID"
        )
        get_account_association.assert_called_once_with(association_id)

    def test_validate_association_id_wrong_user(self, user_service, mocker):
        user = UserFactory.create()
        other_user = UserFactory.create()
        association = OAuthAccountAssociationFactory.create(user=other_user)
        get_account_association = mocker.spy(user_service, "get_account_association")

        form = forms.DeleteAccountAssociationForm(
            MultiDict({"association_id": str(association.id)}),
            user_service=user_service,
            user_id=str(user.id),
        )

        assert not form.validate()
        assert "association_id" in form.errors
        assert (
            form.errors["association_id"][0]
            == "This association does not belong to you"
        )
        get_account_association.assert_called_once_with(str(association.id))
