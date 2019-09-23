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

from datetime import datetime, timedelta, timezone

import pretend
import pytest
import wtforms

from webob.multidict import MultiDict

import warehouse.utils.otp as otp
import warehouse.utils.webauthn as webauthn

from warehouse.manage import forms
from warehouse.packaging.models import Project

from ...common.db.packaging import ProjectFactory, ReleaseFactory


class TestCreateRoleForm:
    def test_creation(self):
        user_service = pretend.stub()
        form = forms.CreateRoleForm(user_service=user_service)

        assert form.user_service is user_service

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
            ("invalid", "Not a valid choice"),
            (None, "Not a valid choice"),
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


class TestAddEmailForm:
    def test_creation(self):
        user_service = pretend.stub()
        form = forms.AddEmailForm(user_service=user_service, user_id=pretend.stub())

        assert form.user_service is user_service

    def test_email_exists_error(self, pyramid_config):
        user_id = pretend.stub()
        form = forms.AddEmailForm(
            data={"email": "foo@bar.com"},
            user_id=user_id,
            user_service=pretend.stub(find_userid_by_email=lambda _: user_id),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "This email address is already being used by this account. "
            "Use a different email."
        )

    def test_email_exists_other_account_error(self, pyramid_config):
        form = forms.AddEmailForm(
            data={"email": "foo@bar.com"},
            user_id=pretend.stub(),
            user_service=pretend.stub(find_userid_by_email=lambda _: pretend.stub()),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "This email address is already being used by another account. "
            "Use a different email."
        )

    def test_blacklisted_email_error(self, pyramid_config):
        form = forms.AddEmailForm(
            data={"email": "foo@bearsarefuzzy.com"},
            user_service=pretend.stub(find_userid_by_email=lambda _: None),
            user_id=pretend.stub(),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "You can't use an email address from this domain. "
            "Use a different email."
        )


class TestChangePasswordForm:
    def test_creation(self):
        user_service = pretend.stub()
        breach_service = pretend.stub()

        form = forms.ChangePasswordForm(
            user_service=user_service, breach_service=breach_service
        )

        assert form.user_service is user_service
        assert form._breach_service is breach_service


class TestProvisionTOTPForm:
    def test_creation(self):
        totp_secret = pretend.stub()
        form = forms.ProvisionTOTPForm(totp_secret=totp_secret)

        assert form.totp_secret is totp_secret

    def test_verify_totp_invalid(self, monkeypatch):
        verify_totp = pretend.call_recorder(lambda *a: False)
        monkeypatch.setattr(otp, "verify_totp", verify_totp)

        form = forms.ProvisionTOTPForm(
            data={"totp_value": "123456"}, totp_secret=pretend.stub()
        )
        assert not form.validate()
        assert form.totp_value.errors.pop() == "Invalid TOTP code. Try again?"

    def test_verify_totp_valid(self, monkeypatch):
        verify_totp = pretend.call_recorder(lambda *a: True)
        monkeypatch.setattr(otp, "verify_totp", verify_totp)

        form = forms.ProvisionTOTPForm(
            data={"totp_value": "123456"}, totp_secret=pretend.stub()
        )
        assert form.validate()


class TestDeleteTOTPForm:
    def test_creation(self):
        user_service = pretend.stub()
        form = forms.DeleteTOTPForm(user_service=user_service)

        assert form.user_service is user_service


class TestProvisionWebAuthnForm:
    def test_creation(self):
        user_service = pretend.stub()
        user_id = pretend.stub()
        challenge = pretend.stub()
        rp_id = pretend.stub()
        origin = pretend.stub()
        form = forms.ProvisionWebAuthnForm(
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

    def test_verify_assertion_invalid_json(self):
        user_service = pretend.stub(
            get_webauthn_by_label=pretend.call_recorder(lambda *a: None)
        )

        form = forms.ProvisionWebAuthnForm(
            data={"credential": "invalid json", "label": "fake label"},
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
                webauthn.RegistrationRejectedException("Fake exception")
            ),
            get_webauthn_by_label=pretend.call_recorder(lambda *a: None),
        )
        form = forms.ProvisionWebAuthnForm(
            data={"credential": "{}", "label": "fake label"},
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
            data={"credential": "{}"},
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
            data={"credential": "{}", "label": "fake label"},
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
            data={"credential": "{}", "label": "fake label"},
            user_service=user_service,
            user_id=pretend.stub(),
            challenge=pretend.stub(),
            rp_id=pretend.stub(),
            origin=pretend.stub(),
        )

        assert form.validate()
        assert form.validated_credential is fake_validated_credential


class TestDeleteWebAuthnForm:
    def test_creation(self):
        user_service = pretend.stub()
        user_id = pretend.stub()
        form = forms.DeleteWebAuthnForm(user_service=user_service, user_id=user_id)

        assert form.user_service is user_service

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
            data={"label": "fake label"},
            user_service=user_service,
            user_id=pretend.stub(),
        )

        assert not form.validate()
        assert form.label.errors.pop() == "No WebAuthn key with given label"

    def test_creates_webauthn_attribute(self):
        fake_webauthn = object()
        user_service = pretend.stub(
            get_webauthn_by_label=pretend.call_recorder(lambda *a: fake_webauthn)
        )
        form = forms.DeleteWebAuthnForm(
            data={"label": "fake label"},
            user_service=user_service,
            user_id=pretend.stub(),
        )

        assert form.validate()
        assert form.webauthn is fake_webauthn


class TestCreateMacaroonForm:
    def test_creation(self):
        user_id = pretend.stub()
        macaroon_service = pretend.stub()
        all_projects = pretend.stub()
        form = forms.CreateMacaroonForm(
            user_id=user_id,
            macaroon_service=macaroon_service,
            all_projects=all_projects,
        )

        assert form.user_id is user_id
        assert form.macaroon_service is macaroon_service
        assert form.all_projects is all_projects

    def test_validate_description_missing(self):
        form = forms.CreateMacaroonForm(
            data={"token_scope": "scope:user"},
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(),
            all_projects=pretend.stub(),
        )

        assert not form.validate()
        assert form.description.errors.pop() == "Specify a token name"

    def test_validate_description_in_use(self):
        form = forms.CreateMacaroonForm(
            data={"description": "dummy", "token_scope": "scope:user"},
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(
                get_macaroon_by_description=lambda *a: pretend.stub()
            ),
            all_projects=pretend.stub(),
        )

        assert not form.validate()
        assert form.description.errors.pop() == "API token name already in use"

    def test_validate_token_scope_missing(self):
        form = forms.CreateMacaroonForm(
            data={"description": "dummy"},
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            all_projects=pretend.stub(),
        )

        assert not form.validate()
        assert form.token_scope.errors.pop() == "Specify the token scope"

    def test_validate_token_scope_unspecified(self):
        form = forms.CreateMacaroonForm(
            data={"description": "dummy", "token_scope": "scope:unspecified"},
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            all_projects=pretend.stub(),
        )

        assert not form.validate()
        assert form.token_scope.errors.pop() == "Specify the token scope"

    @pytest.mark.parametrize(
        ("scope"), ["not a real scope", "scope:project", "scope:foo:bar"]
    )
    def test_validate_token_scope_invalid_format(self, scope):
        form = forms.CreateMacaroonForm(
            data={"description": "dummy", "token_scope": scope},
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            all_projects=pretend.stub(),
        )

        assert not form.validate()
        assert form.token_scope.errors.pop() == f"Unknown token scope: {scope}"

    def test_validate_token_scope_invalid_project(self):
        form = forms.CreateMacaroonForm(
            data={"description": "dummy", "token_scope": "scope:project:foo"},
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            all_projects=[],
        )

        assert not form.validate()
        assert form.token_scope.errors.pop() == "Unknown or invalid project name: foo"

    def test_validate_token_scope_valid_project(self, db_request):
        project = ProjectFactory(name="foo")
        form = forms.CreateMacaroonForm(
            data={"description": "dummy", "token_scope": "scope:project:foo"},
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            all_projects=[project],
        )
        assert form.validate()

    def test_validate_token_scope_valid_project_and_version(self, db_request):
        project = ProjectFactory(name="foo")
        ReleaseFactory.create(project=project, version="1.0.0")
        form = forms.CreateMacaroonForm(
            data={
                "description": "dummy",
                "token_scope": "scope:project:foo",
                "project_version": "1.0.1",
            },
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            all_projects=[project],
        )
        assert form.validate()

    def test_validate_token_scope_not_in_projects(self, db_request):
        project = ProjectFactory(name="foo")
        form = forms.CreateMacaroonForm(
            data={"description": "dummy", "token_scope": "scope:project:foobar"},
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            all_projects=[project],
        )
        assert not form.validate()
        assert (
            form.token_scope.errors.pop() == "Unknown or invalid project name: foobar"
        )

    def test_validate_token_scope_invalid_release(self):
        form = forms.CreateMacaroonForm(
            data={
                "description": "dummy",
                "token_scope": "scope:project:foo",
                "project_version": "AA.BB.CC",
            },
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            all_projects=[],
        )

        assert not form.validate()
        assert form.project_version.errors.pop() == "Invalid version format"

    def test_validate_token_scope_release_in_use(self, db_request):
        project = Project(name="foo")
        ReleaseFactory.create(project=project)
        form = forms.CreateMacaroonForm(
            data={
                "description": "dummy",
                "token_scope": "scope:project:foo",
                "project_version": project.latest_version[0],
            },
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            all_projects=[project],
        )

        assert not form.validate()
        assert form.token_scope.errors.pop() == "Release already exists"

    @pytest.mark.parametrize(
        ["expiration", "valid"],
        [
            ("invalid date", False),
            ((datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"), False),
            ((datetime.now() + timedelta(days=366)).strftime("%Y-%m-%dT%H:%M"), False),
            ((datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"), True),
        ],
    )
    def test_validate_expiration(self, expiration, valid):
        form = forms.CreateMacaroonForm(
            data={
                "description": "dummy",
                "token_scope": "scope:user",
                "expiration": expiration,
            },
            user_id=pretend.stub(),
            macaroon_service=pretend.stub(get_macaroon_by_description=lambda *a: None),
            all_projects=pretend.stub(),
        )

        assert form.validate() == valid
        if valid:
            expiration = datetime.strptime(expiration, "%Y-%m-%dT%H:%M")
            expiration = expiration.astimezone(timezone.utc)
            assert form.validated_caveats["expiration"] == int(expiration.timestamp())


class TestDeleteMacaroonForm:
    def test_creation(self):
        macaroon_service = pretend.stub()
        form = forms.DeleteMacaroonForm(macaroon_service=macaroon_service)

        assert form.macaroon_service is macaroon_service

    def test_validate_macaroon_id_invalid(self):
        macaroon_service = pretend.stub(
            find_macaroon=pretend.call_recorder(lambda id: None)
        )
        form = forms.DeleteMacaroonForm(
            data={"macaroon_id": pretend.stub()}, macaroon_service=macaroon_service
        )

        assert not form.validate()
        assert form.macaroon_id.errors.pop() == "No such macaroon"

    def test_validate_macaroon_id(self):
        macaroon_service = pretend.stub(
            find_macaroon=pretend.call_recorder(lambda id: pretend.stub())
        )
        form = forms.DeleteMacaroonForm(
            data={"macaroon_id": pretend.stub()}, macaroon_service=macaroon_service
        )

        assert form.validate()
