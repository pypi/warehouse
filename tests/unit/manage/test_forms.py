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

from webob.multidict import MultiDict

from warehouse.manage import forms


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
        form = forms.AddEmailForm(user_service=user_service)

        assert form.user_service is user_service


class TestChangePasswordForm:
    def test_creation(self):
        user_service = pretend.stub()
        form = forms.ChangePasswordForm(user_service=user_service)

        assert form.user_service is user_service
