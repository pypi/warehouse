from pretend import stub
from unittest import mock

import pytest

from warehouse.accounts.adapters import Email, EmailAdapter, User, UserAdapter


def test_useradapter_no_username():
    with pytest.raises(ValueError):
        UserAdapter().create(None)


def test_useradapter_creates():
    created = mock.NonCallableMock()
    created.username = "testuser"
    created.set_password = mock.Mock()
    created.save = mock.Mock()
    model = mock.Mock(return_value=created)

    adapter = UserAdapter()
    adapter.model = model

    user = adapter.create("testuser", "testpassword")

    assert user.username == "testuser"

    assert model.call_count == 1
    assert model.call_args == (tuple(), {
                                            "username": "testuser",
                                            "is_staff": False,
                                            "is_superuser": False,
                                            "is_active": True,
                                            "last_login": mock.ANY,
                                            "date_joined": mock.ANY,
                                        })

    assert created.set_password.call_count == 1
    assert created.set_password.call_args == (("testpassword",), {})

    assert created.save.call_count == 1
    assert created.save.call_args == (tuple(), {})


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
    user_model_get = mock.Mock(return_value=user)
    user_model = stub(objects=stub(get=user_model_get))

    created_model_save = mock.Mock()
    created_model = stub(
                        user=user,
                        email="test@example.com",
                        primary=primary if primary is not None else False,
                        verified=verified if verified is not None else False,
                        save=created_model_save,
                    )
    email_model = mock.Mock(return_value=created_model)

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

    assert user_model_get.call_count == 1
    assert user_model_get.call_args == (tuple(), {"username": "testuser"})

    assert email_model.call_count == 1
    assert email_model.call_args == (tuple(), {
                                        "user": user,
                                        "email": "test@example.com",
                                        "primary": primary,
                                        "verified": verified,
                                    })

    assert created_model_save.call_count == 1
    assert created_model_save.call_args == (tuple(), {})


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
