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

from warehouse import accounts

from ..common.db.accounts import UserFactory


def test_password_hasher_attribute():
    passwords = pretend.stub()
    request = pretend.stub(registry={"passwords": passwords})
    assert accounts._pw_hasher(request) is passwords


class TestAuthenticate:

    def test_with_user(self, db_request):
        user = UserFactory.create(session=db_request.db)
        assert accounts._authenticate(user.id, db_request) == []

    def test_without_users(self, db_request):
        assert accounts._authenticate(1, db_request) is None

    def test_wrong_user(self, db_request):
        user = UserFactory.create(session=db_request.db)
        assert accounts._authenticate(user.id + 1, db_request) is None


class TestUser:

    def test_with_user(self, db_request):
        UserFactory.create(session=db_request.db)
        user = UserFactory.create(session=db_request.db)
        UserFactory.create(session=db_request.db)

        db_request.set_property(
            lambda r: user.id, name="unauthenticated_userid"
        )

        assert accounts._user(db_request) is user

    def test_without_users(self, db_request):
        db_request.set_property(lambda r: 1, name="unauthenticated_userid")
        assert accounts._user(db_request) is None

    def test_wrong_user(self, db_request):
        users = [
            UserFactory.create(session=db_request.db),
            UserFactory.create(session=db_request.db),
            UserFactory.create(session=db_request.db),
        ]
        user_id = max(*[u.id for u in users]) + 1

        db_request.set_property(
            lambda r: user_id, name="unauthenticated_userid"
        )

        assert accounts._user(db_request) is None


def test_includeme(monkeypatch):
    authn_obj = pretend.stub()
    authn_cls = pretend.call_recorder(lambda callback: authn_obj)
    authz_obj = pretend.stub()
    authz_cls = pretend.call_recorder(lambda: authz_obj)
    monkeypatch.setattr(accounts, "SessionAuthenticationPolicy", authn_cls)
    monkeypatch.setattr(accounts, "ACLAuthorizationPolicy", authz_cls)

    config = pretend.stub(
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        set_authentication_policy=pretend.call_recorder(lambda p: None),
        set_authorization_policy=pretend.call_recorder(lambda p: None),
        registry={},
    )

    accounts.includeme(config)

    config.add_request_method.calls == [
        pretend.call(accounts._pw_hasher, name="password_hasher", reify=True),
        pretend.call(accounts._user, name="user", reify=True),
    ]
    config.set_authentication_policy.calls == [pretend.call(authn_obj)]
    config.set_authorization_policy.calls == [pretend.call(authz_obj)]
    authn_cls.calls == [pretend.call(callback=accounts._authenticate)]
    authz_cls.calls == [pretend.call()]
