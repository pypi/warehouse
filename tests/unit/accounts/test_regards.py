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
