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

import freezegun
import pretend
import pytest

from warehouse import accounts
from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.services import database_login_factory


class TestLogin:

    def test_with_no_user(self):
        service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: None),
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda iface, context: service),
        )
        assert accounts._login("myuser", "mypass", request) is None
        assert request.find_service.calls == [
            pretend.call(IUserService, context=None),
        ]
        assert service.find_userid.calls == [pretend.call("myuser")]

    def test_with_invalid_password(self):
        userid = pretend.stub()
        service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: userid),
            check_password=pretend.call_recorder(
                lambda userid, password: False
            ),
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda iface, context: service),
        )
        assert accounts._login("myuser", "mypass", request) is None
        assert request.find_service.calls == [
            pretend.call(IUserService, context=None),
        ]
        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.check_password.calls == [pretend.call(userid, "mypass")]

    def test_with_valid_password(self, monkeypatch):
        principals = pretend.stub()
        authenticate = pretend.call_recorder(
            lambda userid, request: principals
        )
        monkeypatch.setattr(accounts, "_authenticate", authenticate)

        userid = pretend.stub()
        service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: userid),
            check_password=pretend.call_recorder(
                lambda userid, password: True
            ),
            update_user=pretend.call_recorder(lambda userid, last_login: None),
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda iface, context: service),
        )

        now = datetime.datetime.utcnow()

        with freezegun.freeze_time(now):
            assert accounts._login("myuser", "mypass", request) is principals

        assert request.find_service.calls == [
            pretend.call(IUserService, context=None),
        ]
        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.check_password.calls == [pretend.call(userid, "mypass")]
        assert service.update_user.calls == [
            pretend.call(userid, last_login=now),
        ]
        assert authenticate.calls == [pretend.call(userid, request)]


class TestAuthenticate:

    @pytest.mark.parametrize(
        ("is_superuser", "expected"),
        [
            (False, []),
            (True, ["group:admins"]),
        ],
    )
    def test_with_user(self, is_superuser, expected):
        user = pretend.stub(is_superuser=is_superuser)
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: user)
        )
        request = pretend.stub(find_service=lambda iface, context: service)

        assert accounts._authenticate(1, request) == expected
        assert service.get_user.calls == [pretend.call(1)]

    def test_without_user(self):
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: None)
        )
        request = pretend.stub(find_service=lambda iface, context: service)

        assert accounts._authenticate(1, request) is None
        assert service.get_user.calls == [pretend.call(1)]


class TestUser:

    def test_with_user(self):
        user = pretend.stub()
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: user)
        )

        request = pretend.stub(
            find_service=lambda iface, context: service,
            authenticated_userid=100,
        )

        assert accounts._user(request) is user
        assert service.get_user.calls == [pretend.call(100)]

    def test_without_users(self):
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: None)
        )

        request = pretend.stub(
            find_service=lambda iface, context: service,
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
            lambda factory, iface, name=None: None
        ),
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        set_authentication_policy=pretend.call_recorder(lambda p: None),
        set_authorization_policy=pretend.call_recorder(lambda p: None),
    )

    accounts.includeme(config)

    config.register_service_factory.calls == [
        pretend.call(database_login_factory, IUserService),
    ]
    config.add_request_method.calls == [
        pretend.call(accounts._user, name="user", reify=True),
    ]
    config.set_authentication_policy.calls == [pretend.call(authn_obj)]
    config.set_authorization_policy.calls == [pretend.call(authz_obj)]
    authn_cls.calls == [pretend.call(callback=accounts._authenticate)]
    authz_cls.calls == [pretend.call()]
