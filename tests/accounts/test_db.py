# Copyright 2013 Donald Stufft
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
from unittest import mock
import datetime
import pytest

import pretend

from warehouse.accounts.tables import users, emails


@pytest.fixture
def user(request, dbapp):

    @request.addfinalizer
    def delete_user():
        dbapp.db.accounts.delete_user(username)

    username = "guidovanrossum"
    email = "notanemail@python.org"
    password = "plaintextpasswordsaregreat"
    dbapp.db.accounts.insert_user(
        username,
        email,
        password)
    return_value = dbapp.db.accounts.get_user(username)
    return_value['password'] = password
    return return_value


def test_get_user(dbapp):
    dbapp.engine.execute(users.insert().values(
        password="!",
        username="test-user",
        name="Test User",
        last_login=datetime.datetime.utcnow(),
        is_active=True,
        is_superuser=False,
        is_staff=False,
    ))

    assert {
        "id": mock.ANY,
        "date_joined": mock.ANY,
        "email": None,
        "name": "Test User",
        "username": "test-user",
    } == dbapp.db.accounts.get_user("test-user")


def test_get_user_with_email(dbapp):
    dbapp.engine.execute(users.insert().values(
        id=1,
        password="!",
        username="test-user",
        name="Test User",
        last_login=datetime.datetime.utcnow(),
        is_active=True,
        is_superuser=False,
        is_staff=False,
    ))
    dbapp.engine.execute(emails.insert().values(
        user_id=1,
        email="test-user@example.com",
        primary=True,
        verified=True,
    ))

    assert {
        "id": 1,
        "date_joined": mock.ANY,
        "email": "test-user@example.com",
        "name": "Test User",
        "username": "test-user",
    } == dbapp.db.accounts.get_user("test-user")


def test_get_user_missing(dbapp):
    assert dbapp.db.accounts.get_user("test-user") is None


def test_user_authenticate(dbapp):
    dbapp.engine.execute(users.insert().values(
        id=1,
        password="hash!",
        username="test-user",
        name="Test User",
        last_login=datetime.datetime.utcnow(),
        is_active=True,
        is_superuser=False,
        is_staff=False,
    ))
    dbapp.passlib.verify_and_update = pretend.call_recorder(
        lambda p, h: (True, None)
    )

    assert dbapp.db.accounts.user_authenticate("test-user", "password")
    assert dbapp.passlib.verify_and_update.calls == [
        pretend.call("password", "hash!"),
    ]


def test_user_authenticate_update(dbapp):
    dbapp.engine.execute(users.insert().values(
        id=1,
        password="hash!",
        username="test-user",
        name="Test User",
        last_login=datetime.datetime.utcnow(),
        is_active=True,
        is_superuser=False,
        is_staff=False,
    ))
    dbapp.passlib.verify_and_update = pretend.call_recorder(
        lambda p, h: (True, "new hash!")
    )

    assert dbapp.db.accounts.user_authenticate("test-user", "password")
    assert dbapp.passlib.verify_and_update.calls == [
        pretend.call("password", "hash!"),
    ]

    r = dbapp.engine.execute("SELECT password FROM accounts_user WHERE id = 1")

    assert list(r) == [("new hash!",)]


def test_user_authenticate_no_user(dbapp):
    assert not dbapp.db.accounts.user_authenticate("test-user", "password")


def test_user_authenticate_exception(engine, dbapp):
    engine.execute(users.insert().values(
        id=1,
        password="hash!",
        username="test-user",
        name="Test User",
        last_login=datetime.datetime.utcnow(),
        is_active=True,
        is_superuser=False,
        is_staff=False,
    ))

    def verify_and_update(password, password_hash):
        raise ValueError("Invalid something or other")
    dbapp.passlib.verify_and_update = verify_and_update

    assert not dbapp.db.accounts.user_authenticate("test-user", "password")


def test_user_authenticate_invalid(engine, dbapp):
    engine.execute(users.insert().values(
        id=1,
        password="hash!",
        username="test-user",
        name="Test User",
        last_login=datetime.datetime.utcnow(),
        is_active=True,
        is_superuser=False,
        is_staff=False,
    ))

    dbapp.passlib.verify_and_update = lambda p, h: (False, None)

    assert not dbapp.db.accounts.user_authenticate("test-user", "password")


def test_insert_and_delete_user(dbapp):
    username = "guidovanrossum"
    email = "notanemail@python.org"
    password = "plaintextpasswordsaregreat"
    dbapp.db.accounts.insert_user(
        username,
        email,
        password
    )
    assert dbapp.db.accounts.user_authenticate(username,
                                               password)
    assert dbapp.db.accounts.get_user(username)
    assert dbapp.db.accounts.get_user_id_by_email(email)
    dbapp.db.accounts.delete_user(username)
    assert not dbapp.db.accounts.get_user(username)


def test_insert_with_same_email(dbapp, user):
    new_username = 'rhodes'
    try:
        dbapp.db.accounts.insert_user(
            new_username,
            user['email'],
            "dummy_password"
        )
        raise AssertionError("Insert user did not return an exception!")
    except ValueError:
        pass
    finally:
        dbapp.db.accounts.delete_user(new_username)


def test_update_user_email(dbapp, user):
    email = "montypython@python.org"
    dbapp.db.accounts.update_user_email(user['id'], email)
    new_info = dbapp.db.accounts.get_user(user['username'])
    assert new_info['email'] == email


def test_update_password(dbapp, user):
    password = "thisisntmyrealpassword"
    dbapp.db.accounts.update_user_password(user['id'], password)
    assert dbapp.db.accounts.user_authenticate(user['username'], password)


def test_update_user(dbapp, user):
    new_password = "test"
    email = "new email"
    dbapp.db.accounts.update_user(user['id'],
                                  password=new_password,
                                  email=email)
    assert dbapp.db.accounts.user_authenticate(user['username'],
                                               new_password)
    new_info = dbapp.db.accounts.get_user(user['username'])
    assert new_info['email'] == email


def test_update_nothing(dbapp, user):
    dbapp.db.accounts.update_user(user['id'])
    info = dbapp.db.accounts.get_user(user['username'])
    assert info['email'] == user['email']
    assert dbapp.db.accounts.user_authenticate(user['username'],
                                               user['password'])
