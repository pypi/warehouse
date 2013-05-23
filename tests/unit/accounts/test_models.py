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
import pytest

from warehouse.accounts.models import User, Email


def test_create_user(db):
    u = User.objects.create_user("testuser", "testpassword")

    assert u
    assert u.is_active
    assert not u.is_staff
    assert not u.is_superuser


def test_create_user_no_username():
    with pytest.raises(ValueError):
        User.objects.create_user(None, None)


def test_create_superuser(db):
    su = User.objects.create_superuser("testsuperuser", "testsuperpassword")

    assert su
    assert su.is_active
    assert su.is_staff
    assert su.is_superuser


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({"username": "testuser1", "name": "Test User #1"}, "Test User #1"),
    ({"username": "testuser2"}, "testuser2"),
])
def test_user_fullname(kwargs, expected, db):
    u = User.objects.create(**kwargs)
    assert u.get_full_name() == expected


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({"username": "testuser1", "name": "Test User #1"}, "Test User #1"),
    ({"username": "testuser2"}, "testuser2"),
])
def test_user_shortname(kwargs, expected, db):
    u = User.objects.create(**kwargs)
    assert u.get_short_name() == expected


def test_users_primary_email_address_verified_primary(db):
    # Create our user
    u = User.objects.create_user("testuser", "testpassword")

    # Create several email addresses for this user
    Email.objects.create(
        user=u, email="test1@example.com", verified=True, primary=False)
    Email.objects.create(
        user=u, email="test2@example.com", verified=True, primary=True)

    assert u.email == "test2@example.com"


def test_users_primary_email_address_unverified_primary(db):
    # Create our user
    u = User.objects.create_user("testuser", "testpassword")

    # Create several email addresses for this user
    Email.objects.create(
        user=u, email="test1@example.com", verified=True, primary=False)
    Email.objects.create(
        user=u, email="test2@example.com", verified=False, primary=True)

    assert u.email is None


def test_users_primary_email_address_no_primary(db):
    # Create our user
    u = User.objects.create_user("testuser", "testpassword")

    # Create several email addresses for this user
    Email.objects.create(
        user=u, email="test1@example.com", verified=True, primary=False)

    assert u.email is None
