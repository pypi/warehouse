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

from warehouse.accounts.forms import LoginForm

from ..common.db.accounts import UserFactory


class TestLoginForm:

    def test_creation(self):
        hasher = pretend.stub()
        db = pretend.stub()
        form = LoginForm(db=db, password_hasher=hasher)

        assert form.db is db
        assert form.password_hasher is hasher
        assert form.user is None

    def test_validate_username_with_no_user(self, db_session):
        form = LoginForm(db=db_session, password_hasher=None)
        field = pretend.stub(data="my_username")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_username(field)

    def test_validate_username_with_user(self, db_session):
        user = UserFactory.create(session=db_session)
        form = LoginForm(db=db_session, password_hasher=None)
        field = pretend.stub(data=user.username)

        form.validate_username(field)

        assert form.user == user

    def test_validate_username_with_user_wrong_case(self, db_session):
        user = UserFactory.create(session=db_session)
        form = LoginForm(db=db_session, password_hasher=None)

        if user.username.upper() != user.username:
            field = pretend.stub(data=user.username.upper())
        else:
            field = pretend.stub(data=user.username.lower())

        form.validate_username(field)

        assert form.user == user

    def test_validate_password_no_user(self):
        field = pretend.stub()
        form = LoginForm(db=None, password_hasher=None)
        form.validate_password(field)

    @pytest.mark.parametrize(
        ("original", "new", "expected"),
        [
            ("hashedpw", None, "hashedpw"),
            ("hashedpw", "newpassword", "newpassword"),
        ],
    )
    def test_validate_password_ok(self, db_session, original, new, expected):
        hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(lambda p, h: (True, new)),
        )
        form = LoginForm(db=None, password_hasher=hasher)
        form.user = UserFactory.create(password=original, session=db_session)
        field = pretend.stub(data="userpw")
        form.validate_password(field)

        assert hasher.verify_and_update.calls == [
            pretend.call("userpw", original),
        ]
        assert form.user.password == expected

    def test_validate_password_notok(self, db_session):
        hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(lambda p, h: (False, None))
        )
        form = LoginForm(db=None, password_hasher=hasher)
        form.user = UserFactory.create(password="hashedpw", session=db_session)
        field = pretend.stub(data="userpw")

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_password(field)

        assert hasher.verify_and_update.calls == [
            pretend.call("userpw", "hashedpw"),
        ]
