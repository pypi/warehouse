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
import uuid

import pytest

from pyramid.authorization import Authenticated

from warehouse.accounts.models import Email, RecoveryCode, User, UserFactory
from warehouse.utils.security_policy import principals_for

from ...common.db.accounts import (
    EmailFactory as DBEmailFactory,
    UserEventFactory as DBUserEventFactory,
    UserFactory as DBUserFactory,
)


class TestUserFactory:
    @pytest.mark.parametrize(
        ("username", "normalized"), [("foo", "foo"), ("Bar", "bar")]
    )
    def test_traversal_finds(self, db_request, username, normalized):
        user = DBUserFactory.create(username=username)
        root = UserFactory(db_request)

        assert root[normalized] == user

    def test_travel_cant_find(self, db_request):
        user = DBUserFactory.create()
        root = UserFactory(db_request)

        with pytest.raises(KeyError):
            root[user.username + "invalid"]

    @pytest.mark.parametrize(
        ("email", "verified", "allowed"),
        [
            ("foo@bar.com", True, True),
            (None, False, False),
            ("foo@bar.com", False, False),
        ],
    )
    def test_has_primary_verified_email(self, db_session, email, verified, allowed):
        user = DBUserFactory.create()

        if email:
            e = Email(email=email, user=user, primary=True, verified=verified)
            db_session.add(e)
            db_session.flush()

        assert user.has_primary_verified_email == allowed


class TestUser:
    def test_get_primary_email_when_no_emails(self, db_session):
        user = DBUserFactory.create()
        assert user.email is None

    def test_get_primary_email(self, db_session):
        user = DBUserFactory.create()
        email = DBEmailFactory.create(user=user, primary=True)
        DBEmailFactory.create(user=user, primary=False)

        assert user.email == email.email

    def test_get_public_email(self, db_session):
        user = DBUserFactory.create()
        email = DBEmailFactory.create(user=user, verified=True, public=True)
        DBEmailFactory.create(user=user, verified=True, public=False)

        assert user.public_email == email

    def test_no_public_email(self, db_session):
        user = DBUserFactory.create()
        DBEmailFactory.create(user=user, primary=True, verified=True)

        assert user.public_email is None

    def test_query_by_email_when_primary(self, db_session):
        user = DBUserFactory.create()
        email = DBEmailFactory.create(user=user, primary=True)

        result = db_session.query(User).filter(User.email == email.email).first()

        assert result == user

    def test_query_by_email_when_not_primary(self, db_session):
        user = DBUserFactory.create()
        email = DBEmailFactory.create(user=user, primary=False)

        result = db_session.query(User).filter(User.email == email.email).first()

        assert result is None

    def test_recent_events(self, db_session):
        user = DBUserFactory.create()
        recent_event = DBUserEventFactory(source=user, tag="foo")
        legacy_event = DBUserEventFactory(
            source=user,
            tag="wu",
            time=datetime.datetime.now() - datetime.timedelta(days=1),
        )
        stale_event = DBUserEventFactory(
            source=user,
            tag="bar",
            time=datetime.datetime.now() - datetime.timedelta(days=91),
        )

        assert user.events.all() == [recent_event, legacy_event, stale_event]
        assert user.recent_events.all() == [recent_event, legacy_event]

    def test_regular_user_not_prohibited_password_reset(self, db_session):
        user = DBUserFactory.create()
        assert user.can_reset_password is True

    def test_superuser_prohibit_password_reset(self, db_session):
        user = DBUserFactory.create(is_superuser=True)
        assert user.can_reset_password is False

    def test_moderator_prohibit_password_reset(self, db_session):
        user = DBUserFactory.create(is_moderator=True)
        assert user.can_reset_password is False

    def test_psf_staff_prohibit_password_reset(self, db_session):
        user = DBUserFactory.create(is_psf_staff=True)
        assert user.can_reset_password is False

    def test_flag_prohibit_password_reset(self, db_session):
        user = DBUserFactory.create(prohibit_password_reset=True)
        assert user.can_reset_password is False

    def test_combo_still_prohibit_password_reset(self, db_session):
        user = DBUserFactory.create(is_superuser=True, prohibit_password_reset=True)
        assert user.can_reset_password is False

    def test_has_burned_recovery_codes(self, db_session):
        user = DBUserFactory.create()
        user.recovery_codes.append(
            RecoveryCode(user_id=user.id, code="hiya", burned=datetime.datetime.now())
        )
        db_session.flush()
        assert user.has_burned_recovery_codes is True

    def test_has_no_burned_recovery_codes(self, db_session):
        user = DBUserFactory.create()
        assert user.has_burned_recovery_codes is False

    def test_acl(self, db_session):
        user = DBUserFactory.create()
        assert user.__acl__() == [
            ("Allow", "group:admins", "admin"),
            ("Allow", "group:moderators", "moderator"),
        ]

    @pytest.mark.parametrize(
        (
            "is_superuser",
            "is_moderator",
            "is_psf_staff",
            "expected",
        ),
        [
            (False, False, False, []),
            (
                True,
                False,
                False,
                ["group:admins", "group:moderators", "group:psf_staff"],
            ),
            (
                False,
                True,
                False,
                ["group:moderators"],
            ),
            (
                True,
                True,
                False,
                ["group:admins", "group:moderators", "group:psf_staff"],
            ),
            (
                False,
                False,
                True,
                ["group:psf_staff"],
            ),
            (
                False,
                True,
                True,
                ["group:moderators", "group:psf_staff"],
            ),
        ],
    )
    def test_principals(
        self,
        is_superuser,
        is_moderator,
        is_psf_staff,
        expected,
    ):
        user = User(
            id=uuid.uuid4(),
            is_superuser=is_superuser,
            is_moderator=is_moderator,
            is_psf_staff=is_psf_staff,
        )

        expected = expected[:] + [f"user:{user.id}", Authenticated]

        assert set(principals_for(user)) == set(expected)
