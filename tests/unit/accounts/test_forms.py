# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import pretend
import pytest

from pretend import stub

from django import forms

from warehouse.accounts.forms import SignupForm, UserChangeForm


def test_signup_form_initalizes():
    SignupForm()


def test_signup_form_clean_username_valid():
    username_exists = pretend.call_recorder(lambda u: False)
    model = stub(api=stub(username_exists=username_exists))
    form = SignupForm({"username": "testuser"})
    form.cleaned_data = {"username": "testuser"}
    form.model = model

    cleaned = form.clean_username()

    assert cleaned == "testuser"
    assert username_exists.calls == [pretend.call("testuser")]


def test_signup_form_clean_username_invalid():
    username_exists = pretend.call_recorder(lambda u: True)
    model = stub(api=stub(username_exists=username_exists))
    form = SignupForm({"username": "testuser"})
    form.cleaned_data = {"username": "testuser"}
    form.model = model

    with pytest.raises(forms.ValidationError):
        form.clean_username()

    assert username_exists.calls == [pretend.call("testuser")]


def test_signup_form_clean_passwords_valid():
    data = {"password": "test password", "confirm_password": "test password"}
    form = SignupForm(data)
    form.cleaned_data = data

    cleaned = form.clean_confirm_password()

    assert cleaned == "test password"


def test_signup_form_clean_passwords_invalid():
    data = {"password": "test password", "confirm_password": "different!"}
    form = SignupForm(data)
    form.cleaned_data = data

    with pytest.raises(forms.ValidationError):
        form.clean_confirm_password()


def test_user_change_form_initalizes():
    UserChangeForm()


def test_user_change_form_clean_password():
    form = UserChangeForm({"password": "fail"}, initial={"password": "epic"})
    assert form.clean_password() == "epic"
