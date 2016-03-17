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

import pretend
import pytest
import wtforms

from warehouse.accounts import forms
from warehouse import recaptcha


class TestLoginForm:

    def test_creation(self):
        user_service = pretend.stub()
        form = forms.LoginForm(user_service=user_service)

        assert form.user_service is user_service

    def test_validate_username_with_no_user(self):
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: None),
        )
        form = forms.LoginForm(user_service=user_service)
        field = pretend.stub(data="my_username")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_username(field)

        assert user_service.find_userid.calls == [pretend.call("my_username")]

    def test_validate_username_with_user(self):
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
        )
        form = forms.LoginForm(user_service=user_service)
        field = pretend.stub(data="my_username")

        form.validate_username(field)

        assert user_service.find_userid.calls == [pretend.call("my_username")]

    def test_validate_password_no_user(self):
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: None),
        )
        form = forms.LoginForm(
            data={"username": "my_username"},
            user_service=user_service,
        )
        field = pretend.stub(data="password")

        form.validate_password(field)

        assert user_service.find_userid.calls == [pretend.call("my_username")]

    def test_validate_password_ok(self):
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=pretend.call_recorder(
                lambda userid, password: True
            ),
        )
        form = forms.LoginForm(
            data={"username": "my_username"},
            user_service=user_service,
        )
        field = pretend.stub(data="pw")

        form.validate_password(field)

        assert user_service.find_userid.calls == [pretend.call("my_username")]
        assert user_service.check_password.calls == [pretend.call(1, "pw")]

    def test_validate_password_notok(self, db_session):
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=pretend.call_recorder(
                lambda userid, password: False
            ),
        )
        form = forms.LoginForm(
            data={"username": "my_username"},
            user_service=user_service,
        )
        field = pretend.stub(data="pw")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(field)

        assert user_service.find_userid.calls == [pretend.call("my_username")]
        assert user_service.check_password.calls == [pretend.call(1, "pw")]


class TestRegistrationForm:
    def test_create(self):
        user_service = pretend.stub()
        recaptcha_service = pretend.stub(enabled=True)

        form = forms.RegistrationForm(
            data={}, user_service=user_service,
            recaptcha_service=recaptcha_service
        )
        assert form.user_service is user_service
        assert form.recaptcha_service is recaptcha_service

    def test_password_confirm_required_error(self):
        form = forms.RegistrationForm(
            data={"password_confirm": ""},
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(
                    lambda _: pretend.stub()
                ),
            ),
            recaptcha_service=pretend.stub(enabled=True),
        )

        assert not form.validate()
        assert form.password_confirm.errors.pop() == "This field is required."

    def test_passwords_mismatch_error(self):
        user_service = pretend.stub(
            find_userid_by_email=pretend.call_recorder(
                lambda _: pretend.stub()
            ),
        )
        form = forms.RegistrationForm(
            data={
                "password": "password",
                "password_confirm": "mismatch",
            },
            user_service=user_service,
            recaptcha_service=pretend.stub(enabled=True),
        )

        assert not form.validate()
        assert form.password_confirm.errors.pop() == "Passwords must match."

    def test_passwords_match_success(self):
        user_service = pretend.stub(
            find_userid_by_email=pretend.call_recorder(
                lambda _: pretend.stub()
            ),
        )
        form = forms.RegistrationForm(
            data={
                "password": "MyStr0ng!shPassword",
                "password_confirm": "MyStr0ng!shPassword",
            },
            user_service=user_service,
            recaptcha_service=pretend.stub(enabled=True),
        )

        form.validate()
        assert len(form.password.errors) == 0
        assert len(form.password_confirm.errors) == 0

    def test_email_required_error(self):
        form = forms.RegistrationForm(
            data={"email": ""},
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(
                    lambda _: pretend.stub()
                ),
            ),
            recaptcha_service=pretend.stub(enabled=True),
        )

        assert not form.validate()
        assert form.email.errors.pop() == "This field is required."

    def test_invalid_email_error(self):
        form = forms.RegistrationForm(
            data={"email": "bad"},
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(lambda _: None),
            ),
            recaptcha_service=pretend.stub(enabled=True),
        )

        assert not form.validate()
        assert form.email.errors.pop() == "Invalid email address."

    def test_email_exists_error(self):
        form = forms.RegistrationForm(
            data={"email": "foo@bar.com"},
            user_service=pretend.stub(
                find_userid_by_email=pretend.call_recorder(
                    lambda _: pretend.stub()
                ),
            ),
            recaptcha_service=pretend.stub(enabled=True),
        )

        assert not form.validate()
        assert form.email.errors.pop() == "Email exists."

    def test_recaptcha_disabled(self):
        form = forms.RegistrationForm(
            data={"g_recpatcha_response": ""},
            user_service=pretend.stub(),
            recaptcha_service=pretend.stub(
                enabled=False,
                verify_response=pretend.call_recorder(lambda _: None),
            ),
        )
        assert not form.validate()
        # there shouldn't be any errors for the recaptcha field if it's
        # disabled
        assert not form.g_recaptcha_response.errors

    def test_recaptcha_required_error(self):
        form = forms.RegistrationForm(
            data={"g_recaptcha_response": ""},
            user_service=pretend.stub(),
            recaptcha_service=pretend.stub(
                enabled=True,
                verify_response=pretend.call_recorder(lambda _: None),
            ),
        )
        assert not form.validate()
        assert form.g_recaptcha_response.errors.pop() \
            == "Recaptcha error."

    def test_recaptcha_error(self):
        form = forms.RegistrationForm(
            data={"g_recaptcha_response": "asd"},
            user_service=pretend.stub(),
            recaptcha_service=pretend.stub(
                verify_response=pretend.raiser(recaptcha.RecaptchaError),
                enabled=True,
            ),
        )
        assert not form.validate()
        assert form.g_recaptcha_response.errors.pop() \
            == "Recaptcha error."

    def test_username_exists(self):
        form = forms.RegistrationForm(
            data={"username": "foo"},
            user_service=pretend.stub(
                find_userid=pretend.call_recorder(lambda name: 1),
            ),
            recaptcha_service=pretend.stub(
                enabled=False,
                verify_response=pretend.call_recorder(lambda _: None),
            ),
        )
        assert not form.validate()
        assert form.username.errors.pop() == "Username exists."

    def test_password_strength(self):
        cases = (
            ("foobar", False),
            ("somethingalittlebetter9", False),
            ("1aDeCent!1", True),
        )
        for pwd, valid in cases:
            form = forms.RegistrationForm(
                data={"password": pwd, "password_confirm": pwd},
                user_service=pretend.stub(),
                recaptcha_service=pretend.stub(
                    enabled=False,
                    verify_response=pretend.call_recorder(lambda _: None),
                ),
            )
            form.validate()
            assert (len(form.password.errors) == 0) == valid
