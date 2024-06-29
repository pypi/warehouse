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

from webob.multidict import MultiDict

import warehouse.utils.otp as otp

from warehouse.accounts import forms
from warehouse.accounts.interfaces import (
    BurnedRecoveryCode,
    InvalidRecoveryCode,
    NoRecoveryCodes,
    TooManyFailedLogins,
)
from warehouse.accounts.models import DisableReason, ProhibitedEmailDomain
from warehouse.captcha import recaptcha
from warehouse.events.tags import EventTag
from warehouse.utils.webauthn import AuthenticationRejectedError


class TestLoginForm:
    def test_validate(self):
        request = pretend.stub(
            remote_addr="1.2.3.4",
            banned=pretend.stub(
                by_ip=lambda ip_address: False,
            ),
        )
        user_service = pretend.stub(
            check_password=lambda userid, password, tags=None: True,
            find_userid=lambda userid: 1,
            is_disabled=lambda id: (False, None),
        )
        breach_service = pretend.stub(
            check_password=pretend.call_recorder(lambda pw, tags: False)
        )
        form = forms.LoginForm(
            MultiDict({"username": "user", "password": "password"}),
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )

        assert form.request is request
        assert form.user_service is user_service
        assert form.breach_service is breach_service
        assert form.validate(), str(form.errors)

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

    @pytest.mark.parametrize(
        "input_username,expected_username",
        [
            ("my_username", "my_username"),
            ("  my_username  ", "my_username"),
            ("my_username ", "my_username"),
            (" my_username", "my_username"),
            ("   my_username    ", "my_username"),
        ],
    )
    def test_validate_username_with_user(self, input_username, expected_username):
        request = pretend.stub()
        user_service = pretend.stub(find_userid=pretend.call_recorder(lambda userid: 1))
        breach_service = pretend.stub()
        form = forms.LoginForm(
            request=request, user_service=user_service, breach_service=breach_service
        )
        field = pretend.stub(data=input_username)
        form.validate_username(field)

        assert user_service.find_userid.calls == [pretend.call(expected_username)]

    def test_validate_password_no_user(self):
        request = pretend.stub(
            remote_addr="1.2.3.4",
            banned=pretend.stub(
                by_ip=lambda ip_address: False,
            ),
        )
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: None)
        )
        breach_service = pretend.stub()
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username"}),
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
        request = pretend.stub(
            remote_addr="1.2.3.4", banned=pretend.stub(by_ip=lambda ip_address: False)
        )
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=pretend.call_recorder(
                lambda userid, password, *args, tags=None: True
            ),
            is_disabled=pretend.call_recorder(
                lambda userid: (True, DisableReason.CompromisedPassword)
            ),
        )
        breach_service = pretend.stub(failure_message="Bad Password!")
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username"}),
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )
        field = pretend.stub(data="pw")

        with pytest.raises(wtforms.validators.ValidationError, match=r"Bad Password\!"):
            form.validate_password(field)

        assert user_service.find_userid.calls == [
            pretend.call("my_username"),
            pretend.call("my_username"),
        ]
        assert user_service.is_disabled.calls == [pretend.call(1)]

    def test_validate_password_ok(self):
        request = pretend.stub(
            remote_addr="1.2.3.4",
            banned=pretend.stub(
                by_ip=lambda ip_address: False,
            ),
        )
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
            formdata=MultiDict({"username": "my_username"}),
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
        request = pretend.stub(
            remote_addr="1.2.3.4",
            banned=pretend.stub(
                by_ip=lambda ip_address: False,
            ),
        )
        user = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        user_service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: user),
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=pretend.call_recorder(
                lambda userid, password, tags=None: False
            ),
            is_disabled=pretend.call_recorder(lambda userid: (False, None)),
        )
        breach_service = pretend.stub()
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username"}),
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )
        field = pretend.stub(data="pw")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(field)

        assert user_service.find_userid.calls == [
            pretend.call("my_username"),
        ]
        assert user_service.is_disabled.calls == []
        assert user_service.check_password.calls == [pretend.call(1, "pw", tags=None)]
        assert user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.LoginFailure,
                request=request,
                additional={"reason": "invalid_password"},
            )
        ]

    def test_validate_password_too_many_failed(self):
        request = pretend.stub(
            remote_addr="1.2.3.4",
            banned=pretend.stub(
                by_ip=lambda ip_address: False,
            ),
        )
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=pretend.call_recorder(
                pretend.raiser(
                    TooManyFailedLogins(resets_in=datetime.timedelta(seconds=600))
                )
            ),
            is_disabled=pretend.call_recorder(lambda userid: (False, None)),
        )
        breach_service = pretend.stub()
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username"}),
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )
        field = pretend.stub(data="pw")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(field)

        assert user_service.find_userid.calls == [
            pretend.call("my_username"),
        ]
        assert user_service.is_disabled.calls == []
        assert user_service.check_password.calls == [pretend.call(1, "pw", tags=None)]

    def test_password_breached(self, monkeypatch):
        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(forms, "send_password_compromised_email_hibp", send_email)

        user = pretend.stub(id=1)
        request = pretend.stub(
            remote_addr="1.2.3.4",
            banned=pretend.stub(
                by_ip=lambda ip_address: False,
            ),
        )
        user_service = pretend.stub(
            find_userid=lambda _: 1,
            get_user=lambda _: user,
            check_password=lambda userid, pw, tags=None: True,
            disable_password=pretend.call_recorder(
                lambda user_id, request, reason=None: None
            ),
            is_disabled=lambda userid: (False, None),
        )
        breach_service = pretend.stub(
            check_password=lambda pw, tags=None: True, failure_message="Bad Password!"
        )

        form = forms.LoginForm(
            MultiDict({"password": "password"}),
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )
        assert not form.validate()
        assert form.password.errors.pop() == "Bad Password!"
        assert user_service.disable_password.calls == [
            pretend.call(
                1,
                request,
                reason=DisableReason.CompromisedPassword,
            )
        ]
        assert send_email.calls == [pretend.call(request, user)]

    def test_validate_password_ok_ip_banned(self):
        request = pretend.stub(
            remote_addr="1.2.3.4",
            banned=pretend.stub(
                by_ip=lambda ip_address: True,
            ),
        )
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
            formdata=MultiDict({"username": "my_username"}),
            request=request,
            user_service=user_service,
            breach_service=breach_service,
            check_password_metrics_tags=["bar"],
        )
        field = pretend.stub(data="pw")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(field)

        assert user_service.find_userid.calls == []
        assert user_service.is_disabled.calls == []
        assert user_service.check_password.calls == []
        assert breach_service.check_password.calls == []

    def test_validate_password_notok_ip_banned(self, db_session):
        request = pretend.stub(
            remote_addr="1.2.3.4",
            banned=pretend.stub(
                by_ip=lambda ip_address: True,
            ),
        )
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=pretend.call_recorder(
                lambda userid, password, tags=None: False
            ),
            is_disabled=pretend.call_recorder(lambda userid: (False, None)),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        breach_service = pretend.stub()
        form = forms.LoginForm(
            formdata=MultiDict({"username": "my_username"}),
            request=request,
            user_service=user_service,
            breach_service=breach_service,
        )
        field = pretend.stub(data="pw")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(field)

        assert user_service.find_userid.calls == []
        assert user_service.is_disabled.calls == []
        assert user_service.check_password.calls == []


class TestRegistrationForm:
    def test_validate(self):
        captcha_service = pretend.stub(
            enabled=False,
            verify_response=pretend.call_recorder(lambda _: None),
        )
        user_service = pretend.stub(
            check_password=lambda userid, password, tags=None: True,
            find_userid=lambda userid: None,
            find_userid_by_email=pretend.call_recorder(lambda email: None),
            is_disabled=lambda id: (False, None),
            username_is_prohibited=lambda a: False,
        )
        breach_service = pretend.stub(
            check_password=pretend.call_recorder(lambda pw, tags: False)
        )

        form = forms.RegistrationForm(
            request=pretend.stub(
                db=pretend.stub(query=lambda *a: pretend.stub(scalar=lambda: False))
            ),
            formdata=MultiDict(
                {
                    "username": "myusername",
                    "new_password": "mysupersecurepassword1!",
                    "password_confirm": "mysupersecurepassword1!",
                    "email": "foo@bar.com",
                    "g_recaptcha_reponse": "",
                }
            ),
            user_service=user_service,
            captcha_service=captcha_service,
            breach_service=breach_service,
        )

        assert form.user_service is user_service
        assert form.captcha_service is captcha_service
        assert form.validate(), str(form.errors)

    def test_password_confirm_required_error(self):
        form = forms.RegistrationForm(
            request=pretend.stub(),
            formdata=MultiDict({"password_confirm": ""}),
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: pretend.stub())
            ),
            captcha_service=pretend.stub(enabled=True),
            breach_service=pretend.stub(check_password=lambda pw: False),
        )

        assert not form.validate()
        assert form.password_confirm.errors.pop() == "This field is required."

    def test_passwords_mismatch_error(self, pyramid_config):
        user_service = pretend.stub(
            find_userid_by_email=pretend.call_recorder(lambda _: pretend.stub())
        )
        form = forms.RegistrationForm(
            request=pretend.stub(),
            formdata=MultiDict(
                {"new_password": "password", "password_confirm": "mismatch"}
            ),
            user_service=user_service,
            captcha_service=pretend.stub(enabled=True),
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
            request=pretend.stub(),
            formdata=MultiDict(
                {
                    "new_password": "MyStr0ng!shPassword",
                    "password_confirm": "MyStr0ng!shPassword",
                }
            ),
            user_service=user_service,
            captcha_service=pretend.stub(enabled=True),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        form.validate()
        assert len(form.new_password.errors) == 0
        assert len(form.password_confirm.errors) == 0

    def test_email_required_error(self):
        form = forms.RegistrationForm(
            request=pretend.stub(),
            formdata=MultiDict({"email": ""}),
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: pretend.stub())
            ),
            captcha_service=pretend.stub(enabled=True),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert form.email.errors.pop() == "This field is required."

    @pytest.mark.parametrize("email", ["bad", "foo]bar@example.com", "</body></html>"])
    def test_invalid_email_error(self, pyramid_request, email):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"email": email}),
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: None)
            ),
            captcha_service=pretend.stub(enabled=True),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop()) == "The email address isn't valid. Try again."
        )

    def test_exotic_email_success(self):
        form = forms.RegistrationForm(
            request=pretend.stub(
                db=pretend.stub(query=lambda *a: pretend.stub(scalar=lambda: False))
            ),
            formdata=MultiDict({"email": "foo@n--tree.net"}),
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: None)
            ),
            captcha_service=pretend.stub(enabled=True),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        form.validate()
        assert len(form.email.errors) == 0

    def test_email_exists_error(self, pyramid_request):
        pyramid_request.db = pretend.stub(
            query=lambda *a: pretend.stub(scalar=lambda: False)
        )
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"email": "foo@bar.com"}),
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: pretend.stub())
            ),
            captcha_service=pretend.stub(enabled=True),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "This email address is already being used by another account. "
            "Use a different email."
        )

    def test_disposable_email_error(self, pyramid_request):
        form = forms.RegistrationForm(
            request=pyramid_request,
            formdata=MultiDict({"email": "foo@bearsarefuzzy.com"}),
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: None)
            ),
            captcha_service=pretend.stub(enabled=True),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert (
            str(form.email.errors.pop())
            == "You can't use an email address from this domain. Use a "
            "different email."
        )

    @pytest.mark.parametrize(
        "email",
        [
            "foo@wutang.net",
            "foo@clan.wutang.net",
            "foo@one.two.wutang.net",
            "foo@wUtAnG.net",
        ],
    )
    def test_prohibited_email_error(self, db_request, email):
        domain = ProhibitedEmailDomain(domain="wutang.net")
        db_request.db.add(domain)

        form = forms.RegistrationForm(
            request=db_request,
            formdata=MultiDict({"email": email}),
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: None)
            ),
            captcha_service=pretend.stub(enabled=True),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert form.email.errors
        assert (
            str(form.email.errors.pop())
            == "You can't use an email address from this domain. Use a "
            "different email."
        )

    def test_recaptcha_disabled(self):
        form = forms.RegistrationForm(
            request=pretend.stub(),
            formdata=MultiDict({"g_recpatcha_response": ""}),
            user_service=pretend.stub(),
            captcha_service=pretend.stub(
                enabled=False,
                verify_response=pretend.call_recorder(lambda _: None),
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )
        assert not form.validate()
        # there shouldn't be any errors for the recaptcha field if it's
        # disabled
        assert not form.g_recaptcha_response.errors

    def test_recaptcha_required_error(self):
        form = forms.RegistrationForm(
            request=pretend.stub(),
            formdata=MultiDict({"g_recaptcha_response": ""}),
            user_service=pretend.stub(),
            captcha_service=pretend.stub(
                enabled=True,
                verify_response=pretend.call_recorder(lambda _: None),
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )
        assert not form.validate()
        assert form.g_recaptcha_response.errors.pop() == "Recaptcha error."

    def test_recaptcha_error(self):
        form = forms.RegistrationForm(
            request=pretend.stub(),
            formdata=MultiDict({"g_recaptcha_response": "asd"}),
            user_service=pretend.stub(),
            captcha_service=pretend.stub(
                verify_response=pretend.raiser(recaptcha.RecaptchaError),
                enabled=True,
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )
        assert not form.validate()
        assert form.g_recaptcha_response.errors.pop() == "Recaptcha error."

    def test_username_exists(self, pyramid_config):
        form = forms.RegistrationForm(
            request=pretend.stub(),
            formdata=MultiDict({"username": "foo"}),
            user_service=pretend.stub(
                find_userid=pretend.call_recorder(lambda name: 1),
                username_is_prohibited=lambda a: False,
            ),
            captcha_service=pretend.stub(
                enabled=False,
                verify_response=pretend.call_recorder(lambda _: None),
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )
        assert not form.validate()
        assert (
            str(form.username.errors.pop())
            == "This username is already being used by another account. "
            "Choose a different username."
        )

    def test_username_prohibted(self, pyramid_config):
        form = forms.RegistrationForm(
            request=pretend.stub(),
            formdata=MultiDict({"username": "foo"}),
            user_service=pretend.stub(
                username_is_prohibited=lambda a: True,
            ),
            captcha_service=pretend.stub(
                enabled=False,
                verify_response=pretend.call_recorder(lambda _: None),
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )
        assert not form.validate()
        assert (
            str(form.username.errors.pop())
            == "This username is already being used by another account. "
            "Choose a different username."
        )

    @pytest.mark.parametrize("username", ["_foo", "bar_", "foo^bar", "boo\0far"])
    def test_username_is_valid(self, username, pyramid_config):
        form = forms.RegistrationForm(
            request=pretend.stub(),
            formdata=MultiDict({"username": username}),
            user_service=pretend.stub(
                find_userid=pretend.call_recorder(lambda _: None),
                username_is_prohibited=lambda a: False,
            ),
            captcha_service=pretend.stub(
                enabled=False,
                verify_response=pretend.call_recorder(lambda _: None),
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
                request=pretend.stub(),
                formdata=MultiDict({"new_password": pwd, "password_confirm": pwd}),
                user_service=pretend.stub(),
                captcha_service=pretend.stub(
                    enabled=False,
                    verify_response=pretend.call_recorder(lambda _: None),
                ),
                breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
            )
            form.validate()
            assert (len(form.new_password.errors) == 0) == valid

    def test_password_breached(self):
        form = forms.RegistrationForm(
            request=pretend.stub(),
            formdata=MultiDict({"new_password": "password"}),
            user_service=pretend.stub(
                find_userid=pretend.call_recorder(lambda _: None)
            ),
            captcha_service=pretend.stub(
                enabled=False,
                verify_response=pretend.call_recorder(lambda _: None),
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
            request=pretend.stub(),
            formdata=MultiDict({"full_name": "hello " * 50}),
            user_service=pretend.stub(
                find_userid=pretend.call_recorder(lambda _: None)
            ),
            captcha_service=pretend.stub(
                enabled=False,
                verify_response=pretend.call_recorder(lambda _: None),
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: True),
        )
        assert not form.validate()
        assert (
            str(form.full_name.errors.pop())
            == "The name is too long. Choose a name with 100 characters or less."
        )

    def test_name_contains_null_bytes(self, pyramid_config):
        form = forms.RegistrationForm(
            request=pretend.stub(),
            formdata=MultiDict({"full_name": "hello\0world"}),
            user_service=pretend.stub(
                find_userid=pretend.call_recorder(lambda _: None)
            ),
            captcha_service=pretend.stub(
                enabled=False,
                verify_response=pretend.call_recorder(lambda _: None),
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: True),
        )
        assert not form.validate()
        assert form.full_name.errors.pop() == "Null bytes are not allowed."


class TestRequestPasswordResetForm:
    @pytest.mark.parametrize(
        "form_input",
        [
            "username",
            "foo@bar.net",
        ],
    )
    def test_validate(self, form_input):
        form = forms.RequestPasswordResetForm(
            request=pretend.stub(),
            formdata=MultiDict({"username_or_email": form_input}),
        )
        assert form.validate()

    def test_no_password_field(self):
        form = forms.RequestPasswordResetForm()
        assert "password" not in form._fields

    @pytest.mark.parametrize("form_input", ["_username", "foo@bar@net", "foo@"])
    def test_validate_with_invalid_inputs(self, form_input):
        form = forms.RequestPasswordResetForm()
        field = pretend.stub(data=form_input)

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_username_or_email(field)


class TestResetPasswordForm:
    def test_validate(self):
        form = forms.ResetPasswordForm(
            formdata=MultiDict(
                {
                    "new_password": "MyStr0ng!shPassword",
                    "password_confirm": "MyStr0ng!shPassword",
                    "username": "username",
                    "full_name": "full_name",
                    "email": "email",
                }
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert form.validate(), str(form.errors)

    def test_password_confirm_required_error(self):
        form = forms.ResetPasswordForm(
            formdata=MultiDict({"password_confirm": ""}),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert not form.validate()
        assert form.password_confirm.errors.pop() == "This field is required."

    def test_passwords_mismatch_error(self, pyramid_config):
        form = forms.ResetPasswordForm(
            formdata=MultiDict(
                {
                    "new_password": "password",
                    "password_confirm": "mismatch",
                    "username": "username",
                    "full_name": "full_name",
                    "email": "email",
                }
            ),
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
            formdata=MultiDict(
                {
                    "new_password": password,
                    "password_confirm": password,
                    "username": "username",
                    "full_name": "full_name",
                    "email": "email",
                }
            ),
            breach_service=pretend.stub(check_password=lambda pw, tags=None: False),
        )

        assert form.validate() == expected

    def test_password_breached(self):
        form = forms.ResetPasswordForm(
            formdata=MultiDict(
                {
                    "new_password": "MyStr0ng!shPassword",
                    "password_confirm": "MyStr0ng!shPassword",
                    "username": "username",
                    "full_name": "full_name",
                    "email": "email",
                }
            ),
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
    @pytest.mark.parametrize(
        "totp_value",
        [
            "123456",
            "1 2 3 4  5 6",
            "123 456",
        ],
    )
    def test_validate(self, totp_value):
        user = pretend.stub(record_event=pretend.call_recorder(lambda *a, **kw: None))
        get_user = pretend.call_recorder(lambda userid: user)
        request = pretend.stub(remote_addr="1.2.3.4")

        form = forms.TOTPAuthenticationForm(
            formdata=MultiDict({"totp_value": totp_value}),
            request=request,
            user_id=pretend.stub(),
            user_service=pretend.stub(
                check_totp_value=lambda *a: True, get_user=get_user
            ),
        )
        assert form.validate()

    @pytest.mark.parametrize(
        "totp_value, expected_error",
        [
            ("", "This field is required."),
            ("not_a_real_value", "TOTP code must be 6 digits."),
            ("1 2 3 4 5 6 7", "TOTP code must be 6 digits."),
        ],
    )
    def test_totp_secret_not_valid(self, pyramid_config, totp_value, expected_error):
        user = pretend.stub(record_event=pretend.call_recorder(lambda *a, **kw: None))
        get_user = pretend.call_recorder(lambda userid: user)
        request = pretend.stub(remote_addr="1.2.3.4")

        form = forms.TOTPAuthenticationForm(
            formdata=MultiDict({"totp_value": totp_value}),
            request=request,
            user_id=pretend.stub(),
            user_service=pretend.stub(
                check_totp_value=lambda *a: True, get_user=get_user
            ),
        )
        assert not form.validate()
        assert str(form.totp_value.errors.pop()) == expected_error

    @pytest.mark.parametrize(
        "exception, expected_error, reason",
        [
            (otp.InvalidTOTPError, "Invalid TOTP code.", "invalid_totp"),
            (otp.OutOfSyncTOTPError, "Invalid TOTP code.", "invalid_totp"),
        ],
    )
    def test_totp_secret_raises(
        self, pyramid_config, exception, expected_error, reason
    ):
        user = pretend.stub(record_event=pretend.call_recorder(lambda *a, **kw: None))
        get_user = pretend.call_recorder(lambda userid: user)
        request = pretend.stub(remote_addr="1.2.3.4")

        user_service = pretend.stub(
            check_totp_value=pretend.raiser(exception),
            get_user=get_user,
        )
        form = forms.TOTPAuthenticationForm(
            formdata=MultiDict({"totp_value": "123456"}),
            request=request,
            user_id=1,
            user_service=user_service,
        )
        assert not form.validate()
        assert str(form.totp_value.errors.pop()) == expected_error
        assert user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.LoginFailure,
                request=request,
                additional={"reason": reason},
            )
        ]


class TestWebAuthnAuthenticationForm:
    def test_credential_valid(self):
        request = pretend.stub()
        challenge = (pretend.stub(),)
        origin = (pretend.stub(),)
        rp_id = (pretend.stub(),)
        form = forms.WebAuthnAuthenticationForm(
            formdata=MultiDict({"credential": json.dumps({})}),
            request=request,
            user_id=pretend.stub(),
            user_service=pretend.stub(
                verify_webauthn_assertion=pretend.call_recorder(
                    lambda *a, **kw: ("foo", 123456)
                )
            ),
            challenge=challenge,
            origin=origin,
            rp_id=rp_id,
        )

        assert form.challenge is challenge
        assert form.origin is origin
        assert form.rp_id is rp_id
        assert form.validate(), str(form.errors)
        assert form.validated_credential == ("foo", 123456)

    def test_credential_bad_payload(self, pyramid_config):
        request = pretend.stub()
        form = forms.WebAuthnAuthenticationForm(
            formdata=MultiDict({"credential": "not valid json"}),
            request=request,
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
        request = pretend.stub(remote_addr="127.0.0.1")
        user = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        user_service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: user),
            verify_webauthn_assertion=pretend.raiser(
                AuthenticationRejectedError("foo")
            ),
        )
        form = forms.WebAuthnAuthenticationForm(
            formdata=MultiDict({"credential": json.dumps({})}),
            request=request,
            user_id=1,
            user_service=user_service,
            challenge=pretend.stub(),
            origin=pretend.stub(),
            rp_id=pretend.stub(),
        )
        assert not form.validate()
        assert form.credential.errors.pop() == "foo"
        assert user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.LoginFailure,
                request=request,
                additional={"reason": "invalid_webauthn"},
            )
        ]


class TestReAuthenticateForm:
    def test_validate(self):
        user_service = pretend.stub(
            find_userid=lambda userid: 1,
            check_password=lambda userid, password, tags=None: True,
        )
        request = pretend.stub()

        form = forms.ReAuthenticateForm(
            formdata=MultiDict(
                {
                    "username": "username",
                    "password": "mysupersecurepassword1!",
                    "next_route": pretend.stub(),
                    "next_route_matchdict": pretend.stub(),
                    "next_route_query": pretend.stub(),
                }
            ),
            request=request,
            user_service=user_service,
        )

        assert form.user_service is user_service
        assert form.__params__ == [
            "username",
            "password",
            "next_route",
            "next_route_matchdict",
            "next_route_query",
        ]
        assert isinstance(form.username, wtforms.StringField)
        assert isinstance(form.next_route, wtforms.StringField)
        assert isinstance(form.next_route_matchdict, wtforms.StringField)
        assert form.validate(), str(form.errors)


class TestRecoveryCodeForm:
    def test_validate(self, monkeypatch):
        request = pretend.stub(remote_addr="1.2.3.4")
        user = pretend.stub(id=pretend.stub(), username="foobar")
        user_service = pretend.stub(
            check_recovery_code=pretend.call_recorder(lambda *a, **kw: True),
            get_user=lambda _: user,
        )
        form = forms.RecoveryCodeAuthenticationForm(
            formdata=MultiDict({"recovery_code_value": "deadbeef00001111"}),
            request=request,
            user_id=user.id,
            user_service=user_service,
        )
        send_recovery_code_used_email = pretend.call_recorder(
            lambda request, user: None
        )
        monkeypatch.setattr(
            forms, "send_recovery_code_used_email", send_recovery_code_used_email
        )

        assert form.request is request
        assert form.user_id is user.id
        assert form.user_service is user_service
        assert form.validate()
        assert send_recovery_code_used_email.calls == [pretend.call(request, user)]

    def test_missing_value(self):
        request = pretend.stub()
        form = forms.RecoveryCodeAuthenticationForm(
            formdata=MultiDict({"recovery_code_value": ""}),
            request=request,
            user_id=pretend.stub(),
            user_service=pretend.stub(),
        )
        assert not form.validate()
        assert form.recovery_code_value.errors.pop() == "This field is required."

    @pytest.mark.parametrize(
        "exception, expected_reason, expected_error",
        [
            (InvalidRecoveryCode, "invalid_recovery_code", "Invalid recovery code."),
            (NoRecoveryCodes, "invalid_recovery_code", "Invalid recovery code."),
            (
                BurnedRecoveryCode,
                "burned_recovery_code",
                "Recovery code has been previously used.",
            ),
        ],
    )
    def test_invalid_recovery_code(
        self, pyramid_config, exception, expected_reason, expected_error
    ):
        request = pretend.stub(remote_addr="127.0.0.1")
        user = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        user_service = pretend.stub(
            check_recovery_code=pretend.raiser(exception),
            get_user=pretend.call_recorder(lambda userid: user),
        )
        form = forms.RecoveryCodeAuthenticationForm(
            formdata=MultiDict({"recovery_code_value": "deadbeef00001111"}),
            request=request,
            user_id=1,
            user_service=user_service,
        )

        assert not form.validate()
        assert str(form.recovery_code_value.errors.pop()) == expected_error
        assert user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.LoginFailure,
                request=request,
                additional={"reason": expected_reason},
            )
        ]

    @pytest.mark.parametrize(
        "input_string, validates",
        [
            (" deadbeef00001111 ", True),
            ("deadbeef00001111 ", True),
            (" deadbeef00001111", True),
            ("deadbeef00001111", True),
            ("wu-tang", False),
            ("deadbeef00001111 deadbeef11110000", False),
        ],
    )
    def test_recovery_code_string_validation(
        self, monkeypatch, input_string, validates
    ):
        request = pretend.stub(remote_addr="127.0.0.1")
        user = pretend.stub(id=pretend.stub(), username="foobar")
        form = forms.RecoveryCodeAuthenticationForm(
            request=request,
            formdata=MultiDict({"recovery_code_value": input_string}),
            user_id=pretend.stub(),
            user_service=pretend.stub(
                check_recovery_code=pretend.call_recorder(lambda *a, **kw: True),
                get_user=lambda _: user,
            ),
        )
        send_recovery_code_used_email = pretend.call_recorder(
            lambda request, user: None
        )
        monkeypatch.setattr(
            forms, "send_recovery_code_used_email", send_recovery_code_used_email
        )

        assert form.validate() == validates
