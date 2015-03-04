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

from zope.interface.verify import verifyClass

from warehouse.accounts import services
from warehouse.accounts.interfaces import ILoginService

from ..common.db.accounts import UserFactory


class TestDatabaseLoginService:

    def test_verify_service(self):
        assert verifyClass(ILoginService, services.DatabaseLoginService)

    def test_service_creation(self, monkeypatch):
        crypt_context_obj = pretend.stub()
        crypt_context_cls = pretend.call_recorder(
            lambda schemes, deprecated: crypt_context_obj
        )
        monkeypatch.setattr(services, "CryptContext", crypt_context_cls)

        session = pretend.stub()
        service = services.DatabaseLoginService(session)

        assert service.db is session
        assert service.hasher is crypt_context_obj
        assert crypt_context_cls.calls == [
            pretend.call(
                schemes=[
                    "bcrypt_sha256",
                    "bcrypt",
                    "django_bcrypt",
                    "unix_disabled",
                ],
                deprecated=["auto"],
            ),
        ]

    def test_find_userid_nonexistant_user(self, db_session):
        service = services.DatabaseLoginService(db_session)
        assert service.find_userid("my_username") is None

    def test_find_userid_existing_user(self, db_session):
        user = UserFactory.create(session=db_session)
        service = services.DatabaseLoginService(db_session)
        assert service.find_userid(user.username) == user.id

    def test_check_password_nonexistant_user(self, db_session):
        service = services.DatabaseLoginService(db_session)
        assert not service.check_password(1, None)

    def test_check_password_invalid(self, db_session):
        user = UserFactory.create(session=db_session)
        service = services.DatabaseLoginService(db_session)
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
        user = UserFactory.create(session=db_session)
        service = services.DatabaseLoginService(db_session)
        service.hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(lambda l, r: (True, None)),
        )

        assert service.check_password(user.id, "user password")
        assert service.hasher.verify_and_update.calls == [
            pretend.call("user password", user.password),
        ]

    def test_check_password_updates(self, db_session):
        user = UserFactory.create(session=db_session)
        password = user.password
        service = services.DatabaseLoginService(db_session)
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


def test_database_login_factory(monkeypatch):
    service_obj = pretend.stub()
    service_cls = pretend.call_recorder(lambda session: service_obj)
    monkeypatch.setattr(services, "DatabaseLoginService", service_cls)

    context = pretend.stub()
    request = pretend.stub(db=pretend.stub())

    assert services.database_login_factory(context, request) is service_obj
    assert service_cls.calls == [pretend.call(request.db)]
