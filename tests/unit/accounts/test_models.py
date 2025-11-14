# SPDX-License-Identifier: Apache-2.0

import datetime
import uuid

import pytest

from pyramid.authorization import Authenticated

from warehouse.accounts.models import (
    Email,
    RecoveryCode,
    User,
    UserFactory,
    WebAuthn,
)
from warehouse.authnz import Permissions
from warehouse.utils.security_policy import principals_for

from ...common.db.accounts import (
    EmailFactory as DBEmailFactory,
    OAuthAccountAssociationFactory as DBAccountAssociationFactory,
    UserEventFactory as DBUserEventFactory,
    UserFactory as DBUserFactory,
    UserUniqueLoginFactory,
)
from ...common.db.packaging import (
    ProjectFactory as DBProjectFactory,
    RoleFactory as DBRoleFactory,
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
            (
                "Allow",
                "group:admins",
                (
                    Permissions.AdminProjectsWrite,
                    Permissions.AdminUsersRead,
                    Permissions.AdminUsersWrite,
                    Permissions.AdminUsersEmailWrite,
                    Permissions.AdminUsersAccountRecoveryWrite,
                    Permissions.AdminDashboardSidebarRead,
                ),
            ),
            (
                "Allow",
                "group:support",
                (
                    Permissions.AdminUsersRead,
                    Permissions.AdminUsersEmailWrite,
                    Permissions.AdminUsersAccountRecoveryWrite,
                    Permissions.AdminDashboardSidebarRead,
                ),
            ),
            (
                "Allow",
                "group:moderators",
                (Permissions.AdminUsersRead, Permissions.AdminDashboardSidebarRead),
            ),
        ]

    @pytest.mark.parametrize(
        (
            "is_superuser",
            "is_support",
            "is_moderator",
            "is_psf_staff",
            "expected",
        ),
        [
            (False, False, False, False, []),
            (
                True,
                False,
                False,
                False,
                [
                    "group:admins",
                    "group:moderators",
                    "group:observers",
                    "group:psf_staff",
                ],
            ),
            (
                False,
                True,
                False,
                False,
                [
                    "group:support",
                    "group:moderators",
                ],
            ),
            (
                False,
                False,
                True,
                False,
                ["group:moderators"],
            ),
            (
                True,
                False,
                True,
                False,
                [
                    "group:admins",
                    "group:moderators",
                    "group:observers",
                    "group:psf_staff",
                ],
            ),
            (
                False,
                False,
                False,
                True,
                ["group:psf_staff"],
            ),
            (
                False,
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
        is_support,
        is_moderator,
        is_psf_staff,
        expected,
    ):
        user = User(
            id=uuid.uuid4(),
            is_superuser=is_superuser,
            is_support=is_support,
            is_moderator=is_moderator,
            is_psf_staff=is_psf_staff,
        )

        expected = expected[:] + [f"user:{user.id}", Authenticated]

        assert set(principals_for(user)) == set(expected)

    @pytest.mark.parametrize(
        ("has_totp", "count_webauthn", "expected"),
        [
            (False, 0, False),
            (False, 1, True),
            (False, 2, False),
            (True, 0, True),
            (True, 1, False),
            (True, 2, False),
        ],
    )
    def test_has_single_2fa(self, db_session, has_totp, count_webauthn, expected):
        user = DBUserFactory.create(totp_secret=None)
        if has_totp:
            user.totp_secret = b"secret"
        for i in range(count_webauthn):
            user.webauthn.append(
                WebAuthn(
                    user_id=user.id,
                    label=f"label{i}",
                    credential_id=f"foo{i}",
                    public_key=f"bar{i}",
                    sign_count=i,
                )
            )
        db_session.flush()
        assert user.has_single_2fa == expected

    def test_user_projects_is_ordered_by_name(self, db_session):
        user = DBUserFactory.create()
        project1 = DBProjectFactory.create(name="foo")
        DBRoleFactory.create(project=project1, user=user)
        project2 = DBProjectFactory.create(name="bar")
        DBRoleFactory.create(project=project2, user=user)
        project3 = DBProjectFactory.create(name="baz")
        DBRoleFactory.create(project=project3, user=user)

        assert user.projects == [project2, project3, project1]

    def test_account_associations_is_ordered_by_created_desc(self, db_session):
        user = DBUserFactory.create()
        assoc1 = DBAccountAssociationFactory.create(
            user=user, created=datetime.datetime(2020, 1, 1)
        )
        assoc2 = DBAccountAssociationFactory.create(
            user=user, created=datetime.datetime(2021, 1, 1)
        )
        assoc3 = DBAccountAssociationFactory.create(
            user=user, created=datetime.datetime(2022, 1, 1)
        )

        assert user.account_associations == [assoc3, assoc2, assoc1]


class TestUserUniqueLogin:
    def test_repr(self, db_session):
        unique_login = UserUniqueLoginFactory.create()
        assert (
            repr(unique_login)
            == f"<UserUniqueLogin(user={unique_login.user.username!r}, "
            f"ip_address={unique_login.ip_address!r}, "
            f"status={unique_login.status!r})>"
        )
