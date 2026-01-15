# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest
import wtforms

from webob.multidict import MultiDict

import warehouse.utils.otp as otp
import warehouse.utils.webauthn as webauthn

from warehouse.accounts.models import ProhibitedEmailDomain
from warehouse.manage import forms

from ...common.constants import REMOTE_ADDR
from ...common.db.accounts import OAuthAccountAssociationFactory, UserFactory
from ...common.db.organizations import OrganizationFactory
from ...common.db.packaging import ProjectFactory


class TestCreateRoleForm:
    def test_validate(self):
        user_service = pretend.stub(find_userid=pretend.call_recorder(lambda userid: 1))
        form = forms.CreateRoleForm(
            formdata=MultiDict({"role_name": "Owner", "username": "valid_username"}),
            user_service=user_service,
        )

        assert form.user_service is user_service
        assert form.validate(), str(form.errors)

    def test_validate_username_with_no_user(self):
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: None)
        )
        form = forms.CreateRoleForm(user_service=user_service)
        field = pretend.stub(data="my_username")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_username(field)

        assert user_service.find_userid.calls == [pretend.call("my_username")]

    def test_validate_username_with_user(self):
        user_service = pretend.stub(find_userid=pretend.call_recorder(lambda userid: 1))
        form = forms.CreateRoleForm(user_service=user_service)
        field = pretend.stub(data="my_username")

        form.validate_username(field)

        assert user_service.find_userid.calls == [pretend.call("my_username")]

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("", "Select role"),
            ("invalid", "Not a valid choice."),
            (None, "Select role"),
        ],
    )
    def test_validate_role_name_fails(self, value, expected):
        user_service = pretend.stub(find_userid=pretend.call_recorder(lambda userid: 1))
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

        user_service = pretend.stub()
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
    def test_validate(self):
        email = pretend.stub(verified=True, public=False, email="foo@example.com")
        user = pretend.stub(id=1, username=pretend.stub(), emails=[email])
        user_service = pretend.stub(get_user=lambda _: user)
        form = forms.SaveAccountForm(
            name="some name",
            public_email=email.email,
            user_service=user_service,
            user_id=user.id,
        )

        assert form.user_id is user.id
        assert form.user_service is user_service
        assert form.validate(), str(form.errors)

    def test_public_email_unverified(self):
        email = pretend.stub(verified=False, public=False, email=pretend.stub())
        user = pretend.stub(id=1, username=pretend.stub(), emails=[email])
        form = forms.SaveAccountForm(
            name="some name",
            public_email=email.email,
            user_service=pretend.stub(get_user=lambda _: user),
            user_id=user.id,
        )
        assert not form.validate()
        assert "is not a verified email for" in form.public_email.errors.pop()

    def test_name_too_long(self, pyramid_config):
        email = pretend.stub(verified=True, public=False, email="foo@example.com")
        user = pretend.stub(id=1, username=pretend.stub(), emails=[email])
        form = forms.SaveAccountForm(
            name="x" * 101,
            public_email=email.email,
            user_service=pretend.stub(get_user=lambda _: user),
            user_id=user.id,
        )

        assert not form.validate()
        assert (
            str(form.name.errors.pop())
            == "The name is too long. Choose a name with 100 characters or less."
        )


class TestAddEmailForm:
    def test_validate(self, metrics):
        user_id = pretend.stub()
        user_service = pretend.stub(find_userid_by_email=lambda _: None)
        form = forms.AddEmailForm(
            request=pretend.stub(
                db=pretend.stub(query=lambda *a: pretend.stub(scalar=lambda: False)),
                metrics=metrics,
            ),
            formdata=MultiDict({"email": "foo@bar.com"}),
            user_id=user_id,
            user_service=user_service,
        )

        assert form.user_id is user_id
        assert form.user_service is user_service
        assert form.validate(), str(form.errors)

    def test_email_exists_error(self, pyramid_request):
        pyramid_request.db = pretend.stub(
            query=lambda *a: pretend.stub(scalar=lambda: False)
        )
        user_id = pretend.stub()
        form = forms.AddEmailForm(
            request=pyramid_request,
            formdata=MultiDict({"email": "foo@bar.com"}),
            user_id=user_id,
            user_service=pretend.stub(find_userid_by_email=lambda _: user_id),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "This email address is already being used by this account. "
            "Use a different email."
        )

    def test_email_exists_other_account_error(self, pyramid_request):
        pyramid_request.db = pretend.stub(
            query=lambda *a: pretend.stub(scalar=lambda: False)
        )
        form = forms.AddEmailForm(
            request=pyramid_request,
            formdata=MultiDict({"email": "foo@bar.com"}),
            user_id=pretend.stub(),
            user_service=pretend.stub(find_userid_by_email=lambda _: pretend.stub()),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "This email address is already being used by another account. "
            "Use a different email."
        )

    def test_prohibited_email_error(self, pyramid_request):
        pyramid_request.db = pretend.stub(
            query=lambda *a: pretend.stub(scalar=lambda: False)
        )
        form = forms.AddEmailForm(
            request=pyramid_request,
            formdata=MultiDict({"email": "foo@bearsarefuzzy.com"}),
            user_service=pretend.stub(find_userid_by_email=lambda _: None),
            user_id=pretend.stub(),
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
            ("foo@wutang.net", "in.mail.net", "mail.net"),
            ("foo@wutang.net", "in.mail.net", "in.mail.net"),
            (
                "foo@outlook.com",
                "outlook-com.mail.protection.outlook.com",
                "outlook.com",
            ),
        ],
    )
    def test_prohibited_mx_domain_error(
        self,
        monkeypatch,
        db_request,
        email_address,
        mx_record_domain,
        prohibited_domain,
    ):
        """
        Similar to `test_prohibited_email_error()`, checking the MX domain.
        """
        mock_deliverability_info = {"mx": [(10, mx_record_domain)]}

        def mock_function(*args, **kwargs):
            return mock_deliverability_info

        monkeypatch.setattr(
            "email_validator.deliverability.validate_email_deliverability",
            mock_function,
        )

        prohibited_mx_domain = ProhibitedEmailDomain(
            domain=prohibited_domain,
            is_mx_record=True,
        )
        db_request.db.add(prohibited_mx_domain)

        form = forms.AddEmailForm(
            request=db_request,
            formdata=MultiDict({"email": email_address}),
            user_service=pretend.stub(find_userid_by_email=lambda _: None),
            user_id=pretend.stub(),
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

        prohibited_mx_domain = ProhibitedEmailDomain(
            domain=prohibited_domain,
            is_mx_record=False,
        )
        db_request.db.add(prohibited_mx_domain)

        form = forms.AddEmailForm(
            request=db_request,
            formdata=MultiDict({"email": email_address}),
            user_service=pretend.stub(find_userid_by_email=lambda _: None),
            user_id=pretend.stub(),
        )

        assert form.validate()

    def test_email_too_long_error(self, pyramid_request):
        form = forms.AddEmailForm(
            request=pyramid_request,
            formdata=MultiDict({"email": f"{'x' * 300}@bar.com"}),
            user_service=pretend.stub(find_userid_by_email=lambda _: None),
            user_id=pretend.stub(),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop()) == "The email address isn't valid. Try again."
        )


class TestChangePasswordForm:
    def test_validate(self):
        request = pretend.stub()
        user_service = pretend.stub(
            find_userid=lambda *a, **kw: 1, check_password=lambda *a, **kw: True
        )
        breach_service = pretend.stub(check_password=lambda p, tags: False)

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
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )

        assert form.request is request
        assert form.user_service is user_service
        assert form._breach_service is breach_service
        assert form.validate(), str(form.errors)


class TestDeleteTOTPForm:
    """
    Covers ConfirmPasswordForm
    """

    def test_validate_confirm_password(self):
        request = pretend.stub(
            remote_addr=REMOTE_ADDR, banned=pretend.stub(by_ip=lambda ip_address: False)
        )
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=pretend.call_recorder(
                lambda userid, password, tags=None: True
            ),
        )
        form = forms.DeleteTOTPForm(
            formdata=MultiDict({"username": "username", "password": "password"}),
            request=request,
            user_service=user_service,
        )

        assert form.request is request
        assert form.user_service is user_service
        assert form.validate(), str(form.errors)


class TestProvisionTOTPForm:
    def test_validate(self, monkeypatch):
        verify_totp = pretend.call_recorder(lambda *a: True)
        monkeypatch.setattr(otp, "verify_totp", verify_totp)

        totp_secret = pretend.stub()
        form = forms.ProvisionTOTPForm(
            formdata=MultiDict({"totp_value": "000000"}), totp_secret=totp_secret
        )

        assert form.totp_secret is totp_secret
        assert form.validate(), str(form.errors)

    @pytest.mark.parametrize(
        ("exception", "expected_error"),
        [
            (otp.InvalidTOTPError, "Invalid TOTP code. Try again?"),
            (
                otp.OutOfSyncTOTPError,
                "Invalid TOTP code. Your device time may be out of sync.",
            ),
        ],
    )
    def test_verify_totp_invalid(self, monkeypatch, exception, expected_error):
        monkeypatch.setattr(otp, "verify_totp", pretend.raiser(exception))

        form = forms.ProvisionTOTPForm(
            formdata=MultiDict({"totp_value": "123456"}), totp_secret=pretend.stub()
        )
        assert not form.validate()
        assert form.totp_value.errors.pop() == expected_error


class TestDeleteWebAuthnForm:
    def test_validate(self):
        fake_webauthn = object()
        user_id = (pretend.stub(),)
        user_service = pretend.stub(
            get_webauthn_by_label=pretend.call_recorder(lambda *a: fake_webauthn)
        )
        form = forms.DeleteWebAuthnForm(
            formdata=MultiDict({"label": "fake label"}),
            user_service=user_service,
            user_id=user_id,
        )

        assert form.user_service is user_service
        assert form.user_id is user_id
        assert form.validate(), str(form.errors)
        assert form.webauthn is fake_webauthn

    def test_validate_label_missing(self):
        form = forms.DeleteWebAuthnForm(
            user_service=pretend.stub(), user_id=pretend.stub()
        )

        assert not form.validate()
        assert form.label.errors.pop() == "Specify a device name"

    def test_validate_label_not_in_use(self):
        user_service = pretend.stub(
            get_webauthn_by_label=pretend.call_recorder(lambda *a: None)
        )
        form = forms.DeleteWebAuthnForm(
            formdata=MultiDict({"label": "fake label"}),
            user_service=user_service,
            user_id=pretend.stub(),
        )

        assert not form.validate()
        assert form.label.errors.pop() == "No WebAuthn key with given label"


class TestProvisionWebAuthnForm:
    def test_validate(self):
        user_service = pretend.stub(
            verify_webauthn_credential=lambda *a, **kw: pretend.stub(),
            get_webauthn_by_label=lambda *a: None,
        )
        user_id = pretend.stub()
        challenge = pretend.stub()
        rp_id = pretend.stub()
        origin = pretend.stub()
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

    def test_verify_assertion_invalid_json(self):
        user_service = pretend.stub(
            get_webauthn_by_label=pretend.call_recorder(lambda *a: None)
        )

        form = forms.ProvisionWebAuthnForm(
            formdata=MultiDict({"credential": "invalid json", "label": "fake label"}),
            user_service=user_service,
            user_id=pretend.stub(),
            challenge=pretend.stub(),
            rp_id=pretend.stub(),
            origin=pretend.stub(),
        )

        assert not form.validate()
        assert (
            form.credential.errors.pop() == "Invalid WebAuthn credential: Bad payload"
        )

    def test_verify_assertion_invalid(self):
        user_service = pretend.stub(
            verify_webauthn_credential=pretend.raiser(
                webauthn.RegistrationRejectedError("Fake exception")
            ),
            get_webauthn_by_label=pretend.call_recorder(lambda *a: None),
        )
        form = forms.ProvisionWebAuthnForm(
            formdata=MultiDict({"credential": "{}", "label": "fake label"}),
            user_service=user_service,
            user_id=pretend.stub(),
            challenge=pretend.stub(),
            rp_id=pretend.stub(),
            origin=pretend.stub(),
        )

        assert not form.validate()
        assert form.credential.errors.pop() == "Fake exception"

    def test_verify_label_missing(self):
        user_service = pretend.stub(
            verify_webauthn_credential=lambda *a, **kw: pretend.stub()
        )
        form = forms.ProvisionWebAuthnForm(
            formdata=MultiDict({"credential": "{}"}),
            user_service=user_service,
            user_id=pretend.stub(),
            challenge=pretend.stub(),
            rp_id=pretend.stub(),
            origin=pretend.stub(),
        )

        assert not form.validate()
        assert form.label.errors.pop() == "Specify a label"

    def test_verify_label_already_in_use(self):
        user_service = pretend.stub(
            verify_webauthn_credential=lambda *a, **kw: pretend.stub(),
            get_webauthn_by_label=pretend.call_recorder(lambda *a: pretend.stub()),
        )
        form = forms.ProvisionWebAuthnForm(
            formdata=MultiDict({"credential": "{}", "label": "fake label"}),
            user_service=user_service,
            user_id=pretend.stub(),
            challenge=pretend.stub(),
            rp_id=pretend.stub(),
            origin=pretend.stub(),
        )

        assert not form.validate()
        assert form.label.errors.pop() == "Label 'fake label' already in use"

    def test_creates_validated_credential(self):
        fake_validated_credential = object()
        user_service = pretend.stub(
            verify_webauthn_credential=lambda *a, **kw: fake_validated_credential,
            get_webauthn_by_label=pretend.call_recorder(lambda *a: None),
        )
        form = forms.ProvisionWebAuthnForm(
            formdata=MultiDict({"credential": "{}", "label": "fake label"}),
            user_service=user_service,
            user_id=pretend.stub(),
            challenge=pretend.stub(),
            rp_id=pretend.stub(),
            origin=pretend.stub(),
        )

        assert form.validate(), str(form.errors)
        assert form.validated_credential is fake_validated_credential


class TestCreateMacaroonForm:
    @pytest.mark.parametrize("selected_project", [None, "foo"])
    def test_creation(self, selected_project):
        user_id = pretend.stub()
        macaroon_service = pretend.stub(get_macaroon_by_description=lambda *a: None)
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

    def test_validate_description_missing(self):
        form = forms.CreateMacaroonForm(
            formdata=MultiDict({"token_scope": "scope:user"}),
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(),
            project_names=pretend.stub(),
        )

        assert not form.validate()
        assert form.description.errors.pop() == "Specify a token name"

    def test_validate_description_in_use(self):
        form = forms.CreateMacaroonForm(
            formdata=MultiDict({"description": "dummy", "token_scope": "scope:user"}),
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(
                get_macaroon_by_description=lambda *a: pretend.stub()
            ),
            project_names=pretend.stub(),
        )

        assert not form.validate()
        assert form.description.errors.pop() == "API token name already in use"

    def test_validate_token_scope_missing(self):
        form = forms.CreateMacaroonForm(
            formdata=MultiDict({"description": "dummy"}),
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            project_names=pretend.stub(),
        )

        assert not form.validate()
        assert form.token_scope.errors.pop() == "Specify the token scope"

    def test_validate_token_scope_unspecified(self):
        form = forms.CreateMacaroonForm(
            formdata=MultiDict(
                {"description": "dummy", "token_scope": "scope:unspecified"}
            ),
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            project_names=pretend.stub(),
        )

        assert not form.validate()
        assert form.token_scope.errors.pop() == "Specify the token scope"

    @pytest.mark.parametrize(
        ("scope"), ["not a real scope", "scope:project", "scope:foo:bar"]
    )
    def test_validate_token_scope_invalid_format(self, scope):
        form = forms.CreateMacaroonForm(
            formdata=MultiDict({"description": "dummy", "token_scope": scope}),
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            project_names=pretend.stub(),
        )

        assert not form.validate()
        assert form.token_scope.errors.pop() == f"Unknown token scope: {scope}"

    def test_validate_token_scope_invalid_project(self):
        form = forms.CreateMacaroonForm(
            formdata=MultiDict(
                {"description": "dummy", "token_scope": "scope:project:foo"}
            ),
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            project_names=["bar"],
        )

        assert not form.validate()
        assert form.token_scope.errors.pop() == "Unknown or invalid project name: foo"

    def test_validate_token_scope_valid_user(self):
        form = forms.CreateMacaroonForm(
            formdata=MultiDict({"description": "dummy", "token_scope": "scope:user"}),
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            project_names=pretend.stub(),
        )

        assert form.validate()

    def test_validate_token_scope_valid_project(self):
        form = forms.CreateMacaroonForm(
            formdata=MultiDict(
                {"description": "dummy", "token_scope": "scope:project:foo"}
            ),
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            project_names=["foo"],
        )

        assert form.validate()


class TestDeleteMacaroonForm:
    def test_validate(self):
        macaroon_service = pretend.stub(
            find_macaroon=pretend.call_recorder(lambda id: pretend.stub())
        )
        request = pretend.stub()
        user_service = pretend.stub(
            find_userid=lambda *a, **kw: 1, check_password=lambda *a, **kw: True
        )
        form = forms.DeleteMacaroonForm(
            formdata=MultiDict(
                {
                    "password": "password",
                    "username": "username",
                    "macaroon_id": pretend.stub(),
                }
            ),
            request=request,
            macaroon_service=macaroon_service,
            user_service=user_service,
        )

        assert form.request is request
        assert form.macaroon_service is macaroon_service
        assert form.user_service is user_service
        assert form.validate(), str(form.errors)

    def test_validate_macaroon_id_invalid(self):
        macaroon_service = pretend.stub(
            find_macaroon=pretend.call_recorder(lambda id: None)
        )
        user_service = pretend.stub(
            find_userid=lambda *a, **kw: 1, check_password=lambda *a, **kw: True
        )
        request = pretend.stub(
            remote_addr=REMOTE_ADDR, banned=pretend.stub(by_ip=lambda ip_address: False)
        )
        form = forms.DeleteMacaroonForm(
            formdata=MultiDict({"macaroon_id": pretend.stub(), "password": "password"}),
            request=request,
            macaroon_service=macaroon_service,
            user_service=user_service,
            username="username",
        )

        assert not form.validate()
        assert form.macaroon_id.errors.pop() == "No such macaroon"

    def test_validate_macaroon_id(self):
        macaroon_service = pretend.stub(
            find_macaroon=pretend.call_recorder(lambda id: pretend.stub())
        )
        user_service = pretend.stub(
            find_userid=lambda *a, **kw: 1, check_password=lambda *a, **kw: True
        )
        request = pretend.stub(
            remote_addr=REMOTE_ADDR, banned=pretend.stub(by_ip=lambda ip_address: False)
        )
        form = forms.DeleteMacaroonForm(
            formdata=MultiDict(
                {
                    "macaroon_id": pretend.stub(),
                    "username": "username",
                    "password": "password",
                }
            ),
            request=request,
            macaroon_service=macaroon_service,
            user_service=user_service,
        )

        assert form.validate(), str(form.errors)


class TestCreateOrganizationApplicationForm:
    def test_creation(self):
        organization_service = pretend.stub()
        user = pretend.stub()
        form = forms.CreateOrganizationApplicationForm(
            organization_service=organization_service,
            user=user,
        )

        assert form.organization_service is organization_service
        assert form.user is user

    def test_validate_name_with_no_organization(self):
        organization_service = pretend.stub(
            get_organization_applications_by_name=pretend.call_recorder(
                lambda name, submitted_by=None, undecided=False: []
            ),
            find_organizationid=pretend.call_recorder(lambda name: None),
        )
        user = pretend.stub()
        form = forms.CreateOrganizationApplicationForm(
            organization_service=organization_service,
            user=user,
        )
        field = pretend.stub(data="my_organization_name")
        forms._ = lambda string: string

        form.validate_name(field)

        assert organization_service.get_organization_applications_by_name.calls == [
            pretend.call("my_organization_name", submitted_by=user, undecided=True)
        ]
        assert organization_service.find_organizationid.calls == [
            pretend.call("my_organization_name")
        ]

    def test_validate_name_with_existing_application(self, db_session):
        organization_service = pretend.stub(
            get_organization_applications_by_name=pretend.call_recorder(
                lambda name, submitted_by=None, undecided=False: [pretend.stub()]
            ),
            find_organizationid=pretend.call_recorder(lambda name: None),
        )
        user = pretend.stub()
        form = forms.CreateOrganizationApplicationForm(
            organization_service=organization_service,
            user=user,
        )
        field = pretend.stub(data="my_organization_name", errors=[])
        forms._ = lambda string: string

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_name(field)

        assert organization_service.get_organization_applications_by_name.calls == [
            pretend.call("my_organization_name", submitted_by=user, undecided=True)
        ]
        assert organization_service.find_organizationid.calls == [
            pretend.call("my_organization_name")
        ]

    def test_validate_name_with_max_applications(self, db_session):
        organization_service = pretend.stub(
            get_organization_applications_by_name=pretend.call_recorder(
                lambda name, submitted_by=None: []
            ),
            find_organizationid=pretend.call_recorder(lambda name: None),
        )
        user = pretend.stub(organization_applications=[])
        form = forms.CreateOrganizationApplicationForm(
            organization_service=organization_service,
            user=user,
            max_applications=3,
        )
        forms._ = lambda string: string

        form.validate__max_apps(pretend.stub())

        assert form.errors == {}

        assert organization_service.get_organization_applications_by_name.calls == []
        assert organization_service.find_organizationid.calls == []

    def test_validate_name_with_fewer_than_max_applications(self, db_session):
        organization_service = pretend.stub(
            get_organization_applications_by_name=pretend.call_recorder(
                lambda name, submitted_by=None: []
            ),
            find_organizationid=pretend.call_recorder(lambda name: None),
        )
        user = pretend.stub(
            organization_applications=[pretend.stub(), pretend.stub(), pretend.stub()]
        )
        form = forms.CreateOrganizationApplicationForm(
            organization_service=organization_service,
            user=user,
            max_applications=3,
        )
        forms._ = lambda string: string

        form.validate__max_apps(pretend.stub())

        assert form.form_errors == [
            (
                "You have already submitted the maximum number of "
                "Organization requests (3)."
            )
        ]

        assert organization_service.get_organization_applications_by_name.calls == []
        assert organization_service.find_organizationid.calls == []

    def test_validate_name_with_organization(self):
        organization_service = pretend.stub(
            find_organizationid=pretend.call_recorder(lambda name: 1)
        )
        form = forms.CreateOrganizationApplicationForm(
            organization_service=organization_service,
            user=pretend.stub(),
        )
        field = pretend.stub(data="my_organization_name", errors=[])

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_name(field)

        assert organization_service.find_organizationid.calls == [
            pretend.call("my_organization_name")
        ]

    def test_validate_name_with_null_bytes(self):
        organization_service = pretend.stub(
            find_organizationid=pretend.call_recorder(lambda name: None),
        )
        form = forms.CreateOrganizationApplicationForm(
            MultiDict({"name": "test\x00name"}),
            organization_service=organization_service,
            user=pretend.stub(),
        )
        assert not form.validate()
        assert "Null bytes are not allowed." in form.name.errors
        assert organization_service.find_organizationid.calls == []


class TestSaveOrganizationNameForm:
    def test_save(self, pyramid_request):
        pyramid_request.POST = MultiDict({"name": "my_org_name"})
        user = pretend.stub()
        organization_service = pretend.stub(
            find_organizationid=pretend.call_recorder(lambda name: None),
            get_organization_applications_by_name=pretend.call_recorder(
                lambda name, submitted_by=None, undecided=False: []
            ),
        )
        form = forms.SaveOrganizationNameForm(
            pyramid_request.POST, organization_service=organization_service, user=user
        )
        form.validate()
        assert organization_service.find_organizationid.calls == [
            pretend.call("my_org_name")
        ]


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
                        "Start and end with a letter or numeral containing "
                        "only ASCII numeric and '.', '_' and '-'."
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
                        "This project name has already been used. "
                        "Choose a different project name."
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
    def test_validate(self):
        organization_service = pretend.stub()
        user_service = pretend.stub(find_userid=pretend.call_recorder(lambda userid: 1))

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
    def test_validate(self, pyramid_request, name, errors):
        pyramid_request.POST = MultiDict({"name": name})

        team_id = pretend.stub()
        organization_service = pretend.stub(find_teamid=lambda org, name: team_id)

        form = forms.CreateTeamForm(
            pyramid_request.POST,
            team_id=team_id,
            organization_id=pretend.stub(),
            organization_service=organization_service,
        )

        assert form.team_id is team_id
        assert form.organization_service is organization_service
        assert not form.validate() if errors else form.validate(), str(form.errors)
        # NOTE(jleightcap): testing with Regexp validators returns raw LazyString
        # objects in the error dict's values. Just assert on keys.
        assert list(form.errors.keys()) == errors


class TestDeleteAccountAssociationForm:
    def test_validate_association_id_valid(self, db_request):
        user = UserFactory.create()
        association = OAuthAccountAssociationFactory.create(user=user)

        user_service = pretend.stub(
            get_account_association=pretend.call_recorder(lambda _: association)
        )

        form = forms.DeleteAccountAssociationForm(
            MultiDict({"association_id": str(association.id)}),
            user_service=user_service,
            user_id=str(user.id),
        )

        assert form.validate()
        assert form.association == association
        assert user_service.get_account_association.calls == [
            pretend.call(str(association.id))
        ]

    def test_validate_association_id_missing(self):
        user_service = pretend.stub()

        form = forms.DeleteAccountAssociationForm(
            MultiDict({}), user_service=user_service, user_id="some-user-id"
        )

        assert not form.validate()
        assert "association_id" in form.errors
        assert form.errors["association_id"][0] == "Specify an association ID"

    def test_validate_association_id_invalid_uuid(self):
        user_service = pretend.stub(
            get_account_association=pretend.call_recorder(lambda _: None)
        )

        form = forms.DeleteAccountAssociationForm(
            MultiDict({"association_id": "not-a-uuid"}),
            user_service=user_service,
            user_id="some-user-id",
        )

        assert not form.validate()
        assert "association_id" in form.errors
        assert form.errors["association_id"][0] == "Association must be specified by ID"

    def test_validate_association_id_not_found(self):
        user_service = pretend.stub(
            get_account_association=pretend.call_recorder(lambda _: None)
        )

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
        assert user_service.get_account_association.calls == [
            pretend.call(association_id)
        ]

    def test_validate_association_id_wrong_user(self, db_request):
        user = UserFactory.create()
        other_user = UserFactory.create()
        association = OAuthAccountAssociationFactory.create(user=other_user)

        user_service = pretend.stub(
            get_account_association=pretend.call_recorder(lambda _: association)
        )

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
        assert user_service.get_account_association.calls == [
            pretend.call(str(association.id))
        ]
