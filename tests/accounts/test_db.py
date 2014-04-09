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
import datetime

import mock
import pretend

from warehouse.accounts.tables import users, emails


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
