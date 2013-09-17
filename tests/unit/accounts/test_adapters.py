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
from pretend import stub

import mock
import pretend
import pytest

from django.db import transaction

from warehouse.accounts.adapters import Email, EmailAdapter, User, UserAdapter


def test_useradapter_no_username():
    with pytest.raises(ValueError):
        UserAdapter().create(None)


def test_useradapter_creates():
    created = pretend.stub(
        username="testuser",
        set_password=pretend.call_recorder(lambda pw: None),
        save=pretend.call_recorder(lambda: None),
    )
    model = pretend.call_recorder(lambda *args, **kwargs: created)

    adapter = UserAdapter()
    adapter.model = model

    user = adapter.create("testuser", "testpassword")

    assert user.username == "testuser"

    assert model.calls == [
        pretend.call(
            username="testuser",
            is_staff=False,
            is_superuser=False,
            is_active=True,
            last_login=mock.ANY,
            date_joined=mock.ANY,
        )
    ]
    assert created.set_password.calls == [pretend.call("testpassword")]
    assert created.save.calls == [pretend.call()]


@pytest.mark.parametrize(("exists",), [(True,), (False,)])
def test_useradapter_username_exists(exists):
    mexists = pretend.call_recorder(lambda: exists)
    mfilter = pretend.call_recorder(
        lambda *args, **kwargs: pretend.stub(exists=mexists)
    )
    model = stub(objects=stub(filter=mfilter))

    adapter = UserAdapter()
    adapter.model = model

    uexists = adapter.username_exists("testuser")

    assert uexists == exists

    assert mfilter.calls == [pretend.call(username="testuser")]
    assert mexists.calls == [pretend.call()]


def test_useradapter_serializer():
    adapter = UserAdapter()

    user = adapter._serialize(stub(username="testuser"))

    assert isinstance(user, User)
    assert user == ("testuser",)
    assert user.username == "testuser"


@pytest.mark.parametrize(("primary", "verified"), [
    (None, None),
    (None, True),
    (None, False),
    (True, True),
    (True, False),
    (True, None),
    (False, True),
    (False, False),
    (False, None),
])
def test_emailadapter_creates(primary, verified):
    user = stub(username="testuser")
    user_model_get = pretend.call_recorder(lambda **kw: user)
    user_model = stub(objects=stub(get=user_model_get))

    created_model_save = pretend.call_recorder(lambda: None)
    created_model = stub(
                        user=user,
                        email="test@example.com",
                        primary=primary if primary is not None else False,
                        verified=verified if verified is not None else False,
                        save=created_model_save,
                    )
    email_model = pretend.call_recorder(lambda *args, **kwargs: created_model)

    adapter = EmailAdapter(user=user_model)
    adapter.model = email_model

    kwargs = {}
    if primary is not None:
        kwargs["primary"] = primary
    if verified is not None:
        kwargs["verified"] = verified

    email = adapter.create("testuser", "test@example.com", **kwargs)

    primary = primary if primary is not None else False
    verified = verified if verified is not None else False

    assert email.user == "testuser"
    assert email.email == "test@example.com"

    assert user_model_get.calls == [pretend.call(username="testuser")]
    assert email_model.calls == [
        pretend.call(
            user=user,
            email="test@example.com",
            primary=primary,
            verified=verified,
        ),
    ]
    assert created_model_save.calls == [pretend.call()]


def test_emailadapter_serializer():
    adapter = EmailAdapter(user=None)

    email = adapter._serialize(stub(
                        user=stub(username="testuser"),
                        email="test@example.com",
                        primary=True,
                        verified=False,
                    ))

    assert isinstance(email, Email)
    assert email == ("testuser", "test@example.com", True, False)
    assert email.user == "testuser"
    assert email.email == "test@example.com"
    assert email.primary
    assert not email.verified


def test_emailadapter_get_user_emails():
    email_models = [
        stub(
            user=stub(username="testuser"),
            email="test@example.com",
            primary=True,
            verified=True,
        )
    ]

    morder_by = pretend.call_recorder(lambda *args: email_models)
    mselect_related = pretend.call_recorder(
        lambda *args, **kwargs: stub(order_by=morder_by)
    )
    mfilter = pretend.call_recorder(
        lambda **kwargs: stub(select_related=mselect_related)
    )
    model = stub(objects=stub(filter=mfilter))

    adapter = EmailAdapter(user=None)
    adapter.model = model

    emails = list(adapter.get_user_emails("testuser"))

    assert emails == [("testuser", "test@example.com", True, True)]

    assert mfilter.calls == [pretend.call(user__username="testuser")]
    assert mselect_related.calls == [pretend.call("user")]
    assert morder_by.calls == [pretend.call("-primary", "email")]


def test_emailadapter_delete_user_email():
    mdelete = pretend.call_recorder(lambda: None)
    mfilter = pretend.call_recorder(lambda **kwargs: stub(delete=mdelete))
    model = stub(objects=stub(filter=mfilter))

    adapter = EmailAdapter(user=None)
    adapter.model = model

    adapter.delete_user_email("testuser", "test@example.com")

    assert mfilter.calls == [
        pretend.call(
            user__username="testuser",
            email="test@example.com",
            primary=False,
        ),
    ]
    assert mdelete.calls == [pretend.call()]


def test_emailadapter_set_user_primary_email(monkeypatch):
    class fake_atomic(object):
        def __init__(self):
            pass

        def __enter__(self):
            pass

        def __exit__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(transaction, "atomic", fake_atomic)

    mupdate = pretend.call_recorder(lambda **kwargs: 1)
    mfilter = pretend.call_recorder(lambda **kwargs: stub(update=mupdate))
    model = stub(objects=stub(filter=mfilter))

    adapter = EmailAdapter(user=None)
    adapter.model = model

    adapter.set_user_primary_email("testuser", "test@example.com")

    assert mfilter.calls == [
        pretend.call(user__username="testuser"),
        pretend.call(
            user__username="testuser",
            email="test@example.com",
            verified=True,
        ),
    ]
    assert mupdate.calls == [
        pretend.call(primary=False),
        pretend.call(primary=True),
    ]


def test_emailadapter_set_user_primary_email_invalid_email(monkeypatch):
    class fake_atomic(object):
        def __init__(self):
            pass

        def __enter__(self):
            pass

        def __exit__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(transaction, "atomic", fake_atomic)

    mupdate = pretend.call_recorder(lambda **kwargs: 0)
    mfilter = pretend.call_recorder(lambda **kwargs: stub(update=mupdate))
    model = stub(objects=stub(filter=mfilter))

    adapter = EmailAdapter(user=None)
    adapter.model = model

    with pytest.raises(ValueError):
        adapter.set_user_primary_email("testuser", "test@example.com")

    assert mfilter.calls == [
        pretend.call(user__username="testuser"),
        pretend.call(
            user__username="testuser",
            email="test@example.com",
            verified=True,
        )
    ]
    assert mupdate.calls == [
        pretend.call(primary=False),
        pretend.call(primary=True)
    ]
