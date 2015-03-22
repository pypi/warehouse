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
from warehouse.accounts.interfaces import ILoginService
from warehouse.accounts.services import database_login_factory


class TestAuthenticate:

    def test_with_user(self):
        user = pretend.stub()
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: user)
        )
        request = pretend.stub(find_service=lambda iface: service)

        assert accounts._authenticate(1, request) == []
        assert service.get_user.calls == [pretend.call(1)]

    def test_without_user(self):
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: None)
        )
        request = pretend.stub(find_service=lambda iface: service)

        assert accounts._authenticate(1, request) is None
        assert service.get_user.calls == [pretend.call(1)]


class TestUser:

    def test_with_user(self):
        user = pretend.stub()
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: user)
        )

        request = pretend.stub(
            find_service=lambda iface: service,
            authenticated_userid=100,
        )

        assert accounts._user(request) is user
        assert service.get_user.calls == [pretend.call(100)]

    def test_without_users(self):
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: None)
        )

        request = pretend.stub(
            find_service=lambda iface: service,
            authenticated_userid=100,
        )

        assert accounts._user(request) is None
        assert service.get_user.calls == [pretend.call(100)]

    def test_without_userid(self):
        request = pretend.stub(authenticated_userid=None)
        assert accounts._user(request) is None


def test_includeme(monkeypatch):
    authn_obj = pretend.stub()
    authn_cls = pretend.call_recorder(lambda callback: authn_obj)
    authz_obj = pretend.stub()
    authz_cls = pretend.call_recorder(lambda: authz_obj)
    monkeypatch.setattr(accounts, "SessionAuthenticationPolicy", authn_cls)
    monkeypatch.setattr(accounts, "ACLAuthorizationPolicy", authz_cls)

    config = pretend.stub(
        register_service_factory=pretend.call_recorder(
            lambda factory, iface: None
        ),
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        set_authentication_policy=pretend.call_recorder(lambda p: None),
        set_authorization_policy=pretend.call_recorder(lambda p: None),
    )

    accounts.includeme(config)

    config.register_service_factory.calls == [
        pretend.call(database_login_factory, ILoginService),
    ]
    config.add_request_method.calls == [
        pretend.call(accounts._user, name="user", reify=True),
    ]
    config.set_authentication_policy.calls == [pretend.call(authn_obj)]
    config.set_authorization_policy.calls == [pretend.call(authz_obj)]
    authn_cls.calls == [pretend.call(callback=accounts._authenticate)]
    authz_cls.calls == [pretend.call()]
