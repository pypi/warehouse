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

from warehouse.accounts.forms import LoginForm, RegisterForm


class TestLoginForm:

    def test_creation(self):
        login_service = pretend.stub()
        form = LoginForm(login_service=login_service)

        assert form.login_service is login_service

    def test_validate_username_with_no_user(self):
        login_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: None),
        )
        form = LoginForm(login_service=login_service)
        field = pretend.stub(data="my_username")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_username(field)

        assert login_service.find_userid.calls == [pretend.call("my_username")]

    def test_validate_username_with_user(self):
        login_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
        )
        form = LoginForm(login_service=login_service)
        field = pretend.stub(data="my_username")

        form.validate_username(field)

        assert login_service.find_userid.calls == [pretend.call("my_username")]

    def test_validate_password_no_user(self):
        login_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: None),
        )
        form = LoginForm(
            data={"username": "my_username"},
            login_service=login_service,
        )
        field = pretend.stub(data="password")

        form.validate_password(field)

        assert login_service.find_userid.calls == [pretend.call("my_username")]

    def test_validate_password_ok(self):
        login_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=pretend.call_recorder(
                lambda userid, password: True
            ),
        )
        form = LoginForm(
            data={"username": "my_username"},
            login_service=login_service,
        )
        field = pretend.stub(data="pw")

        form.validate_password(field)

        assert login_service.find_userid.calls == [pretend.call("my_username")]
        assert login_service.check_password.calls == [pretend.call(1, "pw")]

    def test_validate_password_notok(self, db_session):
        login_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda userid: 1),
            check_password=pretend.call_recorder(
                lambda userid, password: False
            ),
        )
        form = LoginForm(
            data={"username": "my_username"},
            login_service=login_service,
        )
        field = pretend.stub(data="pw")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(field)

        assert login_service.find_userid.calls == [pretend.call("my_username")]
        assert login_service.check_password.calls == [pretend.call(1, "pw")]


class TestRegisterForm:

    def _get_valid_formdata(self):
        return {
            'email': 'myusername@username.com',
            'username': 'my_username',
            'password': 'foo',
            'confirm': 'foo',
        }

    def test_validate_username_with_user_leading_nonalphanumeric(self):
        data = self._get_valid_formdata()
        data['username'] = '_my_username'
        form = RegisterForm(data=data)
        assert not form.validate()

    def test_validate_username_user_trailing_nonalphanumeric(self):
        data = self._get_valid_formdata()
        data['username'] = 'thisisnotok_'
        form = RegisterForm(data=data)
        assert not form.validate()

    def test_validate_username_user_invalid_character(self):
        data = self._get_valid_formdata()
        data['username'] = 'yes@@no'
        form = RegisterForm(data=data)
        assert not form.validate()

    def test_validate_valid_form(self):
        data = self._get_valid_formdata()
        form = RegisterForm(data=data)
        assert form.validate()
