# Copyright 2014 Donald Stufft
#
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
import pytest
from werkzeug.datastructures import MultiDict
from warehouse import forms
from unittest import mock

from warehouse.accounts.forms import (
    LoginForm,
    RegisterForm,
    UsernameValidator
)


def test_validate_username_valid():
    form = LoginForm(
        MultiDict({"username": "test-user", "password": "p@ssw0rd"}),
        authenticator=lambda username, password: True,
    )
    assert form.validate()


def test_validate_username_invalid():
    form = LoginForm(
        MultiDict({"username": "test-user", "password": "p@ssw0rd"}),
        authenticator=lambda username, password: False,
    )
    assert not form.validate()


def test_validate_register_form():
    form = RegisterForm(
        MultiDict({
            "username": "test-user",
            "email": "testuser@example.com",
            "password": "p@ssw0rd",
            "confirm_password": "p@ssw0rd"
        }),
        is_existing_username=lambda username: False,
        is_existing_email=lambda email: False,
    )
    assert form.validate()


def test_duplicate_email():
    form = RegisterForm(
        MultiDict({
            "username": "test-user",
            "email": "testuser@example.com",
            "password": "p@ssw0rd",
            "confirm_password": "p@ssw0rd"
        }),
        is_existing_username=lambda username: False,
        is_existing_email=lambda email: True
    )
    assert not form.validate()


def test_duplicate_username():
    form = RegisterForm(
        MultiDict({
            "username": "test-user",
            "email": "testuser@example.com",
            "password": "p@ssw0rd",
            "confirm_password": "p@ssw0rd"
        }),
        is_existing_username=lambda username: True,
        is_existing_email=lambda email: False
    )
    assert not form.validate()


def test_non_matching_passwords():
    form = RegisterForm(
        MultiDict({
            "username": "test-user",
            "email": "testuser@example.com",
            "password": "p@ssw0rd",
            "confirm_password": "not_p@ssword"
        }),
        is_existing_username=lambda username: False,
        is_existing_email=lambda email: False
    )
    assert not form.validate()


@pytest.mark.parametrize(
    ("username", "raises_exception"),
    [
        ("A----b", False),
        ("----b", True),
        ("A._-zx", False),
        ("Ajay-", True),
        ("A", False)
    ]
)
def test_username_validator(username, raises_exception):
    username_validator = UsernameValidator()
    field = mock.Mock()
    field.data = username
    if raises_exception:
        with pytest.raises(forms.validators.ValidationError):
            username_validator(mock.ANY, field)
    else:
        username_validator(mock.ANY, field)
