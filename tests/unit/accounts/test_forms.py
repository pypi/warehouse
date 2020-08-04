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

import datetime
import json

import pretend
import pytest
import wtforms

from warehouse.accounts import forms
from warehouse.accounts.interfaces import TooManyFailedLogins
from warehouse.accounts.models import DisableReason
from warehouse.utils.webauthn import AuthenticationRejectedException


class TestLoginForm:
    def test_creation(self):
        request = pretend.stub()
        user_service = pretend.stub()
        breach_service = pretend.stub()
        form = forms.LoginForm(
            request=request, user_service=user_service, breach_service=breach_service
        )

        assert form.request is request
        assert form.user_service is user_service
        assert form.breach_service is breach_service

    def test_validate_username_with_no_user(self):
        request = pretend.stub()
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: None)
        )
        breach_service = pretend.stub()
        form = forms.LoginForm(
            request=request, user_service=user_service, breach_service=breach_service
        )
        field = pretend.stub(data="my_username")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_username(field)

        assert user_service.find_userid.calls == [pretend.call("my_username")]

    def test_validate_username_with_user(self):
        request = pretend.stub()
        user_service = pretend.stub(find_userid=pretend.call_recorder(lambda userid: 1))
        breach_service = pretend.stub()
        form = forms.LoginForm(
            request=request, user_service=user_service, breach_service=breach_service
        )
        field = pretend.stub(data="my_username")

        form.validate_username(field)

        assert user_service.find_userid.calls == [pretend.call("my_username")]

    def test_validate_password_no_user(self):
        request = pretend.stub()
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: None)
        )
        breach_service = pretend.stub()
        form = forms.LoginForm(
            data={"username": "my_username"},
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )
        field = pretend.stub(data="password")

        form.validate_password(field)

        assert user_service.find_userid.calls == [
            pretend.call("my_username"),
            pretend.call("my_username"),
        ]

    def test_validate_password_disabled_for_compromised_pw(self, db_session):
        request = pretend.stub()
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            is_disabled=pretend.call_recorder(
                lambda userid: (True, DisableReason.CompromisedPassword)
            ),
        )
        breach_service = pretend.stub(failure_message="Bad Password!")
        form = forms.LoginForm(
            data={"username": "my_username"},
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )
        field = pretend.stub(data="pw")

        with pytest.raises(wtforms.validators.ValidationError, match=r"Bad Password\!"):
            form.validate_password(field)

        assert user_service.find_userid.calls == [pretend.call("my_username")]
        assert user_service.is_disabled.calls == [pretend.call(1)]

    def test_validate_password_ok(self):
        request = pretend.stub()
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=pretend.call_recorder(
                lambda userid, password, tags=None: True
            ),
            is_disabled=pretend.call_recorder(lambda userid: (False, None)),
        )
        breach_service = pretend.stub(
            check_password=pretend.call_recorder(lambda pw, tags: False)
        )
        form = forms.LoginForm(
            data={"username": "my_username"},
            request=request,
            user_service=user_service,
            breach_service=breach_service,
            check_password_metrics_tags=["bar"],
        )
        field = pretend.stub(data="pw")

        form.validate_password(field)

        assert user_service.find_userid.calls == [
            pretend.call("my_username"),
            pretend.call("my_username"),
        ]
        assert user_service.is_disabled.calls == [pretend.call(1)]
        assert user_service.check_password.calls == [
            pretend.call(1, "pw", tags=["bar"])
        ]
        assert breach_service.check_password.calls == [
            pretend.call("pw", tags=["method:auth", "auth_method:login_form"])
        ]

    def test_validate_password_notok(self, db_session):
        request = pretend.stub()
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=pretend.call_recorder(
                lambda userid, password, tags=None: False
            ),
            is_disabled=pretend.call_recorder(lambda userid: (False, None)),
        )
        breach_service = pretend.stub()
        form = forms.LoginForm(
            data={"username": "my_username"},
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )
        field = pretend.stub(data="pw")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(field)

        assert user_service.find_userid.calls == [
            pretend.call("my_username"),
            pretend.call("my_username"),
        ]
        assert user_service.is_disabled.calls == [pretend.call(1)]
        assert user_service.check_password.calls == [pretend.call(1, "pw", tags=None)]

    def test_validate_password_too_many_failed(self):
        @pretend.call_recorder
        def check_password(userid, password, tags=None):
            raise TooManyFailedLogins(resets_in=datetime.timedelta(seconds=600))

        request = pretend.stub()
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=check_password,
            is_disabled=pretend.call_recorder(lambda userid: (False, None)),
        )
        breach_service = pretend.stub()
        form = forms.LoginForm(
            data={"username": "my_username"},
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )
        field = pretend.stub(data="pw")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(field)

        assert user_service.find_userid.calls == [
            pretend.call("my_username"),
            pretend.call("my_username"),
        ]
        assert user_service.is_disabled.calls == [pretend.call(1)]
        assert user_service.check_password.calls == [pretend.call(1, "pw", tags=None)]

    def test_password_breached(self, monkeypatch):
        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(forms, "send_password_compromised_email_hibp", send_email)

        user = pretend.stub(id=1)
        request = pretend.stub()
        user_service = pretend.stub(
            find_userid=lambda _: 1,
            get_user=lambda _: user,
            check_password=lambda userid, pw, tags=None: True,
            disable_password=pretend.call_recorder(lambda user_id, reason=None: None),
            is_disabled=lambda userid: (False, None),
        )
        breach_service = pretend.stub(
            check_password=lambda pw, tags=None: True, failure_message="Bad Password!"
        )

        form = forms.LoginForm(
            data={"password": "password"},
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert form.password.errors.pop() == "Bad Password!"
        assert user_service.disable_password.calls == [
            pretend.call(1, reason=DisableReason.CompromisedPassword)
        ]
        assert send_email.calls == [pretend.call(request, user)]


class TestRegistrationForm:
    def test_create(self):
        user_service = pretend.stub()
        breach_service = pretend.stub()

        form = forms.RegistrationForm(
            data={}, user_service=user_service, breach_service=breach_service
        )
        assert form.user_service is user_service

    def test_password_confirm_required_error(self):
        form = forms.RegistrationForm(
            data={"password_confirm": ""},
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: pretend.stub())
            ),
            breach_service=pretend.stub(check_password=lambda pw: False),
        )

        assert not form.validate()
        assert form.password_confirm.errors.pop() == "This field is required."

    def test_passwords_mismatch_error(self, pyramid_config):
        user_service = pretend.stub(
            find_userid_by_email=pretend.call_recorder(lambda _: pretend.stub())
        )
        form = forms.RegistrationForm(
            data={"new_password": "password", "password_confirm": "mismatch"},
            user_service=user_service,
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert (
            str(form.password_confirm.errors.pop())
            == "Your passwords don't match. Try again."
        )

    def test_passwords_match_success(self):
        user_service = pretend.stub(
            find_userid_by_email=pretend.call_recorder(lambda _: pretend.stub())
        )
        form = forms.RegistrationForm(
            data={
                "new_password": "MyStr0ng!shPassword",
                "password_confirm": "MyStr0ng!shPassword",
            },
            user_service=user_service,
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        form.validate()
        assert len(form.new_password.errors) == 0
        assert len(form.password_confirm.errors) == 0

    def test_email_required_error(self):
        form = forms.RegistrationForm(
            data={"email": ""},
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: pretend.stub())
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert form.email.errors.pop() == "This field is required."

    @pytest.mark.parametrize("email", ["bad", "foo]bar@example.com"])
    def test_invalid_email_error(self, pyramid_config, email):
        form = forms.RegistrationForm(
            data={"email": email},
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: None)
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop()) == "The email address isn't valid. Try again."
        )

    def test_exotic_email_success(self):
        form = forms.RegistrationForm(
            data={"email": "foo@n--tree.net"},
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: None)
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        form.validate()
        assert len(form.email.errors) == 0

    def test_email_exists_error(self, pyramid_config):
        form = forms.RegistrationForm(
            data={"email": "foo@bar.com"},
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: pretend.stub())
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "This email address is already being used by another account. "
            "Use a different email."
        )

    def test_prohibited_email_error(self, pyramid_config):
        form = forms.RegistrationForm(
            data={"email": "foo@bearsarefuzzy.com"},
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: None)
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "You can't use an email address from this domain. Use a "
            "different email."
        )

    def test_username_exists(self, pyramid_config):
        form = forms.RegistrationForm(
            data={"username": "foo"},
            user_service=pretend.stub(
                find_userid=pretend.call_recorder(lambda name: 1)
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )
        assert not form.validate()
        assert (
            str(form.username.errors.pop())
            == "This username is already being used by another account. "
            "Choose a different username."
        )

    @pytest.mark.parametrize("username", ["_foo", "bar_", "foo^bar"])
    def test_username_is_valid(self, username, pyramid_config):
        form = forms.RegistrationForm(
            data={"username": username},
            user_service=pretend.stub(
                find_userid=pretend.call_recorder(lambda _: None)
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )
        assert not form.validate()
        assert (
            str(form.username.errors.pop()) == "The username is invalid. Usernames "
            "must be composed of letters, numbers, "
            "dots, hyphens and underscores. And must "
            "also start and finish with a letter or number. "
            "Choose a different username."
        )

    def test_password_strength(self):
        cases = (
            ("foobar", False),
            ("somethingalittlebetter9", True),
            ("1aDeCent!1", True),
        )
        for pwd, valid in cases:
            form = forms.RegistrationForm(
                data={"new_password": pwd, "password_confirm": pwd},
                user_service=pretend.stub(),
                breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
            )
            form.validate()
            assert (len(form.new_password.errors) == 0) == valid

    def test_password_breached(self):
        form = forms.RegistrationForm(
            data={"new_password": "password"},
            user_service=pretend.stub(
                find_userid=pretend.call_recorder(lambda _: None)
            ),
            breach_service=pretend.stub(
                check_password=lambda pw, tags=None: True,
                failure_message=(
                    "This password has appeared in a breach or has otherwise been "
                    "compromised and cannot be used."
                ),
            ),
        )
        assert not form.validate()
        assert form.new_password.errors.pop() == (
            "This password has appeared in a breach or has otherwise been "
            "compromised and cannot be used."
        )

    def test_name_too_long(self, pyramid_config):
        form = forms.RegistrationForm(
            data={"full_name": "hello " * 50},
            user_service=pretend.stub(
                find_userid=pretend.call_recorder(lambda _: None)
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: True),
        )
        assert not form.validate()
        assert (
            str(form.full_name.errors.pop())
            == "The name is too long. Choose a name with 100 characters or less."
        )


class TestRequestPasswordResetForm:
    def test_creation(self):
        user_service = pretend.stub()
        form = forms.RequestPasswordResetForm(user_service=user_service)
        assert form.user_service is user_service

    def test_no_password_field(self):
        user_service = pretend.stub()
        form = forms.RequestPasswordResetForm(user_service=user_service)
        assert "password" not in form._fields

    def test_validate_username_or_email(self):
        user_service = pretend.stub(
            get_user_by_username=pretend.call_recorder(lambda userid: "1"),
            get_user_by_email=pretend.call_recorder(lambda userid: "1"),
        )
        form = forms.RequestPasswordResetForm(user_service=user_service)
        field = pretend.stub(data="username_or_email")

        form.validate_username_or_email(field)

        assert user_service.get_user_by_username.calls == [
            pretend.call("username_or_email")
        ]

    def test_validate_username_or_email_with_none(self):
        user_service = pretend.stub(
            get_user_by_username=pretend.call_recorder(lambda userid: None),
            get_user_by_email=pretend.call_recorder(lambda userid: None),
        )
        form = forms.RequestPasswordResetForm(user_service=user_service)
        field = pretend.stub(data="username_or_email")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_username_or_email(field)

        assert user_service.get_user_by_username.calls == [
            pretend.call("username_or_email")
        ]

        assert user_service.get_user_by_email.calls == [
            pretend.call("username_or_email")
        ]


class TestResetPasswordForm:
    def test_password_confirm_required_error(self):
        form = forms.ResetPasswordForm(
            data={"password_confirm": ""},
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert form.password_confirm.errors.pop() == "This field is required."

    def test_passwords_mismatch_error(self, pyramid_config):
        form = forms.ResetPasswordForm(
            data={
                "new_password": "password",
                "password_confirm": "mismatch",
                "username": "username",
                "full_name": "full_name",
                "email": "email",
            },
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert (
            str(form.password_confirm.errors.pop())
            == "Your passwords don't match. Try again."
        )

    @pytest.mark.parametrize(
        ("password", "expected"),
        [("foobar", False), ("somethingalittlebetter9", True), ("1aDeCent!1", True)],
    )
    def test_password_strength(self, password, expected):
        form = forms.ResetPasswordForm(
            data={
                "new_password": password,
                "password_confirm": password,
                "username": "username",
                "full_name": "full_name",
                "email": "email",
            },
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert form.validate() == expected

    def test_passwords_match_success(self):
        form = forms.ResetPasswordForm(
            data={
                "new_password": "MyStr0ng!shPassword",
                "password_confirm": "MyStr0ng!shPassword",
                "username": "username",
                "full_name": "full_name",
                "email": "email",
            },
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert form.validate()

    def test_password_breached(self):
        form = forms.ResetPasswordForm(
            data={
                "new_password": "MyStr0ng!shPassword",
                "password_confirm": "MyStr0ng!shPassword",
                "username": "username",
                "full_name": "full_name",
                "email": "email",
            },
            user_service=pretend.stub(
                find_userid=pretend.call_recorder(lambda _: None)
            ),
            breach_service=pretend.stub(
                check_password=lambda pw, tags=None: True,
                failure_message=(
                    "This password has appeared in a breach or has otherwise been "
                    "compromised and cannot be used."
                ),
            ),
        )
        assert not form.validate()
        assert form.new_password.errors.pop() == (
            "This password has appeared in a breach or has otherwise been "
            "compromised and cannot be used."
        )


class TestTOTPAuthenticationForm:
    def test_creation(self):
        user_id = pretend.stub()
        user_service = pretend.stub()
        form = forms.TOTPAuthenticationForm(user_id=user_id, user_service=user_service)

        assert form.user_service is user_service

    def test_totp_secret_exists(self, pyramid_config):
        form = forms.TOTPAuthenticationForm(
            data={"totp_value": ""}, user_id=pretend.stub(), user_service=pretend.stub()
        )
        assert not form.validate()
        assert form.totp_value.errors.pop() == "This field is required."

        form = forms.TOTPAuthenticationForm(
            data={"totp_value": "not_a_real_value"},
            user_id=pretend.stub(),
            user_service=pretend.stub(check_totp_value=lambda *a: True),
        )
        assert not form.validate()
        assert str(form.totp_value.errors.pop()) == "TOTP code must be 6 digits."

        form = forms.TOTPAuthenticationForm(
            data={"totp_value": "1 2 3 4 5 6 7"},
            user_id=pretend.stub(),
            user_service=pretend.stub(check_totp_value=lambda *a: True),
        )
        assert not form.validate()
        assert str(form.totp_value.errors.pop()) == "TOTP code must be 6 digits."

        form = forms.TOTPAuthenticationForm(
            data={"totp_value": "123456"},
            user_id=pretend.stub(),
            user_service=pretend.stub(check_totp_value=lambda *a: False),
        )
        assert not form.validate()
        assert str(form.totp_value.errors.pop()) == "Invalid TOTP code."

        form = forms.TOTPAuthenticationForm(
            data={"totp_value": "123456"},
            user_id=pretend.stub(),
            user_service=pretend.stub(check_totp_value=lambda *a: True),
        )
        assert form.validate()

        form = forms.TOTPAuthenticationForm(
            data={"totp_value": " 1 2 3 4  5 6 "},
            user_id=pretend.stub(),
            user_service=pretend.stub(check_totp_value=lambda *a: True),
        )
        assert form.validate()

        form = forms.TOTPAuthenticationForm(
            data={"totp_value": "123 456"},
            user_id=pretend.stub(),
            user_service=pretend.stub(check_totp_value=lambda *a: True),
        )
        assert form.validate()


class TestWebAuthnAuthenticationForm:
    def test_creation(self):
        user_id = pretend.stub()
        user_service = pretend.stub()
        challenge = pretend.stub()
        origin = pretend.stub()
        rp_id = pretend.stub()

        form = forms.WebAuthnAuthenticationForm(
            user_id=user_id,
            user_service=user_service,
            challenge=challenge,
            origin=origin,
            rp_id=rp_id,
        )

        assert form.challenge is challenge

    def test_credential_bad_payload(self, pyramid_config):
        form = forms.WebAuthnAuthenticationForm(
            credential="not valid json",
            user_id=pretend.stub(),
            user_service=pretend.stub(),
            challenge=pretend.stub(),
            origin=pretend.stub(),
            rp_id=pretend.stub(),
        )
        assert not form.validate()
        assert (
            str(form.credential.errors.pop())
            == "Invalid WebAuthn assertion: Bad payload"
        )

    def test_credential_invalid(self):
        form = forms.WebAuthnAuthenticationForm(
            credential=json.dumps({}),
            user_id=pretend.stub(),
            user_service=pretend.stub(
                verify_webauthn_assertion=pretend.raiser(
                    AuthenticationRejectedException("foo")
                )
            ),
            challenge=pretend.stub(),
            origin=pretend.stub(),
            rp_id=pretend.stub(),
        )
        assert not form.validate()
        assert form.credential.errors.pop() == "foo"

    def test_credential_valid(self):
        form = forms.WebAuthnAuthenticationForm(
            credential=json.dumps({}),
            user_id=pretend.stub(),
            user_service=pretend.stub(
                verify_webauthn_assertion=pretend.call_recorder(
                    lambda *a, **kw: ("foo", 123456)
                )
            ),
            challenge=pretend.stub(),
            origin=pretend.stub(),
            rp_id=pretend.stub(),
        )
        assert form.validate()
        assert form.validated_credential == ("foo", 123456)


class TestReAuthenticateForm:
    def test_creation(self):
        user_service = pretend.stub()

        form = forms.ReAuthenticateForm(user_service=user_service)

        assert form.user_service is user_service
        assert form.__params__ == [
            "username",
            "password",
            "next_route",
            "next_route_matchdict",
        ]
        assert isinstance(form.username, wtforms.StringField)
        assert isinstance(form.next_route, wtforms.StringField)
        assert isinstance(form.next_route_matchdict, wtforms.StringField)


class TestRecoveryCodeForm:
    def test_creation(self):
        user_id = pretend.stub()
        user_service = pretend.stub()
        form = forms.RecoveryCodeAuthenticationForm(
            user_id=user_id, user_service=user_service
        )

        assert form.user_id is user_id
        assert form.user_service is user_service

    def test_missing_value(self):
        form = forms.RecoveryCodeAuthenticationForm(
            data={"recovery_code_value": ""},
            user_id=pretend.stub(),
            user_service=pretend.stub(),
        )
        assert not form.validate()
        assert form.recovery_code_value.errors.pop() == "This field is required."

    def test_invalid_recovery_code(self, pyramid_config):
        form = forms.RecoveryCodeAuthenticationForm(
            data={"recovery_code_value": "invalid"},
            user_id=pretend.stub(),
            user_service=pretend.stub(
                check_recovery_code=pretend.call_recorder(lambda *a, **kw: False)
            ),
        )

        assert not form.validate()
        assert str(form.recovery_code_value.errors.pop()) == "Invalid recovery code."

    def test_valid_recovery_code(self):
        form = forms.RecoveryCodeAuthenticationForm(
            data={"recovery_code_value": "valid"},
            user_id=pretend.stub(),
            user_service=pretend.stub(
                check_recovery_code=pretend.call_recorder(lambda *a, **kw: True)
            ),
        )

        assert form.validate()
