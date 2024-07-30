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

from pyramid.authorization import Allow
from pyramid.interfaces import ISecurityPolicy
from pyramid.security import Denied
from zope.interface.verify import verifyClass

from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.utils import UserContext
from warehouse.authnz import Permissions
from warehouse.macaroons import security_policy
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.services import InvalidMacaroonError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.utils import PublisherTokenContext


@pytest.mark.parametrize(
    ["auth", "result"],
    [
        (None, None),
        ("notarealtoken", None),
        ("maybeafuturemethod foobar", None),
        ("token foobar", "foobar"),
        ("bearer foobar", "foobar"),
        ("basic X190b2tlbl9fOmZvb2Jhcg==", "foobar"),  # "__token__:foobar"
    ],
)
def test_extract_http_macaroon(auth, result, metrics):
    request = pretend.stub(
        find_service=pretend.call_recorder(lambda *a, **kw: metrics),
        headers=pretend.stub(get=pretend.call_recorder(lambda k: auth)),
    )

    assert security_policy._extract_http_macaroon(request) == result


@pytest.mark.parametrize(
    ["auth", "result"],
    [
        ("notbase64", None),
        ("bm90YXJlYWx0b2tlbg==", None),  # "notarealtoken"
        ("QGJhZHVzZXI6Zm9vYmFy", None),  # "@baduser:foobar"
        ("X190b2tlbl9fOmZvb2Jhcg==", "foobar"),  # "__token__:foobar"
        ("X190b2tlbl9fOiBmb29iYXIgCg==", "foobar"),  # "__token__: foobar "
    ],
)
def test_extract_basic_macaroon(auth, result):
    assert security_policy._extract_basic_macaroon(auth) == result


class TestMacaroonSecurityPolicy:
    def test_verify(self):
        assert verifyClass(
            ISecurityPolicy,
            security_policy.MacaroonSecurityPolicy,
        )

    def test_noops(self):
        policy = security_policy.MacaroonSecurityPolicy()
        with pytest.raises(NotImplementedError):
            policy.authenticated_userid(pretend.stub())

    def test_forget_and_remember(self):
        policy = security_policy.MacaroonSecurityPolicy()

        assert policy.forget(pretend.stub()) == []
        assert policy.remember(pretend.stub(), pretend.stub()) == []

    def test_identity_no_http_macaroon(self, monkeypatch):
        policy = security_policy.MacaroonSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        extract_http_macaroon = pretend.call_recorder(lambda r: None)
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", extract_http_macaroon
        )

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None)
        )

        assert policy.identity(request) is None
        assert extract_http_macaroon.calls == [pretend.call(request)]

        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity_no_db_macaroon(self, monkeypatch):
        policy = security_policy.MacaroonSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        raw_macaroon = pretend.stub()
        extract_http_macaroon = pretend.call_recorder(lambda r: raw_macaroon)
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", extract_http_macaroon
        )

        macaroon_service = pretend.stub(
            find_from_raw=pretend.call_recorder(pretend.raiser(InvalidMacaroonError)),
        )

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            find_service=pretend.call_recorder(lambda iface, **kw: macaroon_service),
        )

        assert policy.identity(request) is None
        assert extract_http_macaroon.calls == [pretend.call(request)]
        assert request.find_service.calls == [
            pretend.call(IMacaroonService, context=None),
        ]
        assert macaroon_service.find_from_raw.calls == [pretend.call(raw_macaroon)]

        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity_disabled_user(self, monkeypatch):
        policy = security_policy.MacaroonSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        raw_macaroon = pretend.stub()
        extract_http_macaroon = pretend.call_recorder(lambda r: raw_macaroon)
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", extract_http_macaroon
        )

        user = pretend.stub(id="deadbeef-dead-beef-deadbeef-dead")
        macaroon = pretend.stub(user=user, oidc_publisher=None)
        macaroon_service = pretend.stub(
            find_from_raw=pretend.call_recorder(lambda rm: macaroon),
        )

        user_service = pretend.stub(
            is_disabled=pretend.call_recorder(lambda user_id: (True, Exception)),
        )

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            find_service=pretend.call_recorder(
                lambda iface, **kw: {
                    IMacaroonService: macaroon_service,
                    IUserService: user_service,
                }[iface]
            ),
        )

        assert policy.identity(request) is None
        assert extract_http_macaroon.calls == [pretend.call(request)]
        assert request.find_service.calls == [
            pretend.call(IMacaroonService, context=None),
            pretend.call(IUserService, context=None),
        ]
        assert macaroon_service.find_from_raw.calls == [pretend.call(raw_macaroon)]
        assert user_service.is_disabled.calls == [
            pretend.call("deadbeef-dead-beef-deadbeef-dead")
        ]

        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity_user(self, monkeypatch):
        policy = security_policy.MacaroonSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        raw_macaroon = pretend.stub()
        extract_http_macaroon = pretend.call_recorder(lambda r: raw_macaroon)
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", extract_http_macaroon
        )

        user = pretend.stub(id="deadbeef-dead-beef-deadbeef-dead")
        macaroon = pretend.stub(user=user, oidc_publisher=None)
        macaroon_service = pretend.stub(
            find_from_raw=pretend.call_recorder(lambda rm: macaroon),
        )

        user_service = pretend.stub(
            is_disabled=pretend.call_recorder(lambda user_id: (False, Exception)),
        )

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            find_service=pretend.call_recorder(
                lambda iface, **kw: {
                    IMacaroonService: macaroon_service,
                    IUserService: user_service,
                }[iface]
            ),
        )

        assert policy.identity(request) == UserContext(user, macaroon)
        assert extract_http_macaroon.calls == [pretend.call(request)]
        assert request.find_service.calls == [
            pretend.call(IMacaroonService, context=None),
            pretend.call(IUserService, context=None),
        ]
        assert macaroon_service.find_from_raw.calls == [pretend.call(raw_macaroon)]
        assert user_service.is_disabled.calls == [
            pretend.call("deadbeef-dead-beef-deadbeef-dead")
        ]

        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity_oidc_publisher(self, monkeypatch):
        policy = security_policy.MacaroonSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        raw_macaroon = pretend.stub()
        extract_http_macaroon = pretend.call_recorder(lambda r: raw_macaroon)
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", extract_http_macaroon
        )

        oidc_publisher = pretend.stub()
        oidc_additional = {"oidc": {"foo": "bar"}}
        macaroon = pretend.stub(
            user=None, oidc_publisher=oidc_publisher, additional=oidc_additional
        )
        macaroon_service = pretend.stub(
            find_from_raw=pretend.call_recorder(lambda rm: macaroon),
        )

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            find_service=pretend.call_recorder(lambda iface, **kw: macaroon_service),
        )

        identity = policy.identity(request)
        assert identity
        assert identity.publisher is oidc_publisher
        assert identity == PublisherTokenContext(
            oidc_publisher, SignedClaims(oidc_additional["oidc"])
        )

        assert extract_http_macaroon.calls == [pretend.call(request)]
        assert request.find_service.calls == [
            pretend.call(IMacaroonService, context=None),
            pretend.call(IUserService, context=None),
        ]
        assert macaroon_service.find_from_raw.calls == [pretend.call(raw_macaroon)]

        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_permits_invalid_macaroon(self, monkeypatch):
        macaroon_service = pretend.stub(
            verify=pretend.raiser(InvalidMacaroonError("foo"))
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda interface, **kw: macaroon_service)
        )
        _extract_http_macaroon = pretend.call_recorder(lambda r: "not a real macaroon")
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        policy = security_policy.MacaroonSecurityPolicy()
        result = policy.permits(request, pretend.stub(), Permissions.ProjectsUpload)

        assert result == Denied("")
        assert result.s == "Invalid API Token: foo"

    @pytest.mark.parametrize(
        "principals,expected", [(["user:5"], True), (["user:1"], False)]
    )
    def test_permits_valid_macaroon(self, monkeypatch, principals, expected):
        macaroon_service = pretend.stub(
            verify=pretend.call_recorder(lambda *a: pretend.stub())
        )
        request = pretend.stub(
            identity=pretend.stub(__principals__=lambda: principals),
            find_service=pretend.call_recorder(
                lambda interface, **kw: macaroon_service
            ),
        )
        _extract_http_macaroon = pretend.call_recorder(lambda r: "not a real macaroon")
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        context = pretend.stub(
            __acl__=[(Allow, "user:5", [Permissions.ProjectsUpload])]
        )

        policy = security_policy.MacaroonSecurityPolicy()
        result = policy.permits(request, context, Permissions.ProjectsUpload)

        assert bool(result) == expected

    @pytest.mark.parametrize(
        "invalid_permission",
        [Permissions.AccountManage, Permissions.ProjectsWrite, "nonexistent"],
    )
    def test_denies_valid_macaroon_for_incorrect_permission(
        self, monkeypatch, invalid_permission
    ):
        _extract_http_macaroon = pretend.call_recorder(lambda r: "not a real macaroon")
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        policy = security_policy.MacaroonSecurityPolicy()
        result = policy.permits(pretend.stub(), pretend.stub(), invalid_permission)

        assert result == Denied("")
        assert result.s == (
            f"API tokens are not valid for permission: {invalid_permission}!"
        )
