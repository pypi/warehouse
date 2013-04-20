from pretend import stub
from unittest import mock

from warehouse.accounts.regards import UserCreator


def test_user_creator_basic():
    UserCreator()


def test_user_creator():
    user_creator = mock.Mock(return_value=stub(username="testuser"))
    email_creator = mock.Mock(return_value=stub(email="test@example.com"))
    mailer = mock.Mock()

    creator = UserCreator(
                user_creator=user_creator,
                email_creator=email_creator,
                mailer=mailer,
            )

    user = creator("testuser", "test@example.com", "testpassword")

    assert user.username == "testuser"

    assert user_creator.call_count == 1
    assert user_creator.call_args == (("testuser", "testpassword"), {})

    assert email_creator.call_count == 1
    assert email_creator.call_args == (("testuser", "test@example.com"), {})
