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

import uuid

import pretend

from zope.interface.verify import verifyClass

from warehouse.accounts import services
from warehouse.accounts.interfaces import IUserService

from ...common.db.accounts import UserFactory, EmailFactory


class TestDatabaseUserService:

    def test_verify_service(self):
        assert verifyClass(IUserService, services.DatabaseUserService)

    def test_service_creation(self, monkeypatch):
        crypt_context_obj = pretend.stub()
        crypt_context_cls = pretend.call_recorder(
            lambda **kwargs: crypt_context_obj
        )
        monkeypatch.setattr(services, "CryptContext", crypt_context_cls)

        session = pretend.stub()
        service = services.DatabaseUserService(session)

        assert service.db is session
        assert service.hasher is crypt_context_obj
        assert crypt_context_cls.calls == [
            pretend.call(
                schemes=[
                    "bcrypt_sha256",
                    "argon2",
                    "bcrypt",
                    "django_bcrypt",
                    "unix_disabled",
                ],
                deprecated=[
                    "bcrypt",
                    "django_bcrypt",
                    "unix_disabled",
                ],
                truncate_error=True,
                argon2__memory_cost=1024,
                argon2__parallelism=6,
                argon2__time_cost=6,
            ),
        ]

    def test_find_userid_nonexistant_user(self, db_session):
        service = services.DatabaseUserService(db_session)
        assert service.find_userid("my_username") is None

    def test_find_userid_existing_user(self, db_session):
        user = UserFactory.create()
        service = services.DatabaseUserService(db_session)
        assert service.find_userid(user.username) == user.id

    def test_check_password_nonexistant_user(self, db_session):
        service = services.DatabaseUserService(db_session)
        assert not service.check_password(uuid.uuid4(), None)

    def test_check_password_invalid(self, db_session):
        user = UserFactory.create()
        service = services.DatabaseUserService(db_session)
        service.hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(
                lambda l, r: (False, None)
            ),
        )

        assert not service.check_password(user.id, "user password")
        assert service.hasher.verify_and_update.calls == [
            pretend.call("user password", user.password),
        ]

    def test_check_password_valid(self, db_session):
        user = UserFactory.create()
        service = services.DatabaseUserService(db_session)
        service.hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(lambda l, r: (True, None)),
        )

        assert service.check_password(user.id, "user password")
        assert service.hasher.verify_and_update.calls == [
            pretend.call("user password", user.password),
        ]

    def test_check_password_updates(self, db_session):
        user = UserFactory.create()
        password = user.password
        service = services.DatabaseUserService(db_session)
        service.hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(
                lambda l, r: (True, "new password")
            ),
        )

        assert service.check_password(user.id, "user password")
        assert service.hasher.verify_and_update.calls == [
            pretend.call("user password", password),
        ]
        assert user.password == "new password"

    def test_create_user(self, db_session):
        user = UserFactory.build()
        email = "foo@example.com"
        service = services.DatabaseUserService(db_session)
        new_user = service.create_user(username=user.username,
                                       name=user.name,
                                       password=user.password,
                                       email=email)
        db_session.flush()
        user_from_db = service.get_user(new_user.id)
        assert user_from_db.username == user.username
        assert user_from_db.name == user.name
        assert user_from_db.email == email

    def test_update_user(self, db_session):
        user = UserFactory.create()
        service = services.DatabaseUserService(db_session)
        new_name = "new username"
        service.update_user(user.id, username=new_name)
        user_from_db = service.get_user(user.id)
        assert user_from_db.username == user.username

    def test_verify_email(self, db_session):
        service = services.DatabaseUserService(db_session)
        user = UserFactory.create()
        EmailFactory.create(user=user, primary=True,
                            verified=False)
        EmailFactory.create(user=user, primary=False,
                            verified=False)
        service.verify_email(user.id, user.emails[0].email)
        assert user.emails[0].verified
        assert not user.emails[1].verified

    def test_find_by_email(self, db_session):
        service = services.DatabaseUserService(db_session)
        user = UserFactory.create()
        EmailFactory.create(user=user, primary=True, verified=False)

        found_userid = service.find_userid_by_email(user.emails[0].email)
        db_session.flush()

        assert user.id == found_userid

    def test_find_by_email_not_found(self, db_session):
        service = services.DatabaseUserService(db_session)
        assert service.find_userid_by_email("something") is None

    def test_create_login_success(self, db_session):
        service = services.DatabaseUserService(db_session)
        user = service.create_user(
            "test_user", "test_name", "test_password", "test_email")

        assert user.id is not None
        # now make sure that we can log in as that user
        assert service.check_password(user.id, "test_password")

    def test_create_login_error(self, db_session):
        service = services.DatabaseUserService(db_session)
        user = service.create_user(
            "test_user", "test_name", "test_password", "test_email")

        assert user.id is not None
        assert not service.check_password(user.id, "bad_password")


def test_database_login_factory(monkeypatch):
    service_obj = pretend.stub()
    service_cls = pretend.call_recorder(lambda session: service_obj)
    monkeypatch.setattr(services, "DatabaseUserService", service_cls)

    context = pretend.stub()
    request = pretend.stub(db=pretend.stub())

    assert services.database_login_factory(context, request) is service_obj
    assert service_cls.calls == [pretend.call(request.db)]
