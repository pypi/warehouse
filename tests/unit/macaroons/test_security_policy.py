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

from pyramid.interfaces import IAuthorizationPolicy, ISecurityPolicy
from pyramid.security import Denied
from zope.interface.verify import verifyClass

from warehouse.macaroons import security_policy
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.services import InvalidMacaroonError


@pytest.mark.parametrize(
    ["auth", "result"],
    [
        (None, None),
        ("notarealtoken", None),
        ("maybeafuturemethod foobar", None),
        ("token foobar", "foobar"),
        ("basic X190b2tlbl9fOmZvb2Jhcg==", "foobar"),  # "__token__:foobar"
    ],
)
def test_extract_http_macaroon(auth, result):
    request = pretend.stub(
        headers=pretend.stub(get=pretend.call_recorder(lambda k: auth))
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
        assert policy.authenticated_userid(pretend.stub()) == NotImplemented
        assert (
            policy.permits(pretend.stub(), pretend.stub(), pretend.stub())
            == NotImplemented
        )

    def test_forget_and_remember(self):
        policy = security_policy.MacaroonSecurityPolicy()

        assert policy.forget(pretend.stub()) == []
        assert policy.remember(pretend.stub(), pretend.stub()) == []

    def test_identify_no_macaroon(self, monkeypatch):
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

    def test_identify(self, monkeypatch):
        policy = security_policy.MacaroonSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        raw_macaroon = pretend.stub()
        extract_http_macaroon = pretend.call_recorder(lambda r: raw_macaroon)
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", extract_http_macaroon
        )

        user = pretend.stub()
        macaroon_service = pretend.stub(
            find_from_raw=pretend.call_recorder(lambda m: pretend.stub(user=user))
        )
        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            find_service=pretend.call_recorder(lambda i, **kw: macaroon_service),
        )

        assert policy.identity(request) is user
        assert extract_http_macaroon.calls == [pretend.call(request)]
        assert request.find_service.calls == [
            pretend.call(IMacaroonService, context=None)
        ]
        assert macaroon_service.find_from_raw.calls == [pretend.call(raw_macaroon)]

        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]


class TestMacaroonAuthorizationPolicy:
    def test_verify(self):
        assert verifyClass(
            IAuthorizationPolicy, security_policy.MacaroonAuthorizationPolicy
        )

    def test_permits_no_active_request(self, monkeypatch):
        get_current_request = pretend.call_recorder(lambda: None)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: pretend.stub())
        )
        policy = security_policy.MacaroonAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == Denied("")
        assert result.s == "There was no active request."

    def test_permits_no_macaroon(self, monkeypatch):
        request = pretend.stub()
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        _extract_http_macaroon = pretend.call_recorder(lambda r: None)
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        permits = pretend.stub()
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits)
        )
        policy = security_policy.MacaroonAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == permits

    def test_permits_invalid_macaroon(self, monkeypatch):
        macaroon_service = pretend.stub(
            verify=pretend.raiser(InvalidMacaroonError("foo"))
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda interface, **kw: macaroon_service)
        )
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        _extract_http_macaroon = pretend.call_recorder(lambda r: b"not a real macaroon")
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        permits = pretend.stub()
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits)
        )
        policy = security_policy.MacaroonAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == Denied("")
        assert result.s == "Invalid API Token: InvalidMacaroonError('foo')"

    def test_permits_valid_macaroon(self, monkeypatch):
        macaroon_service = pretend.stub(
            verify=pretend.call_recorder(lambda *a: pretend.stub())
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda interface, **kw: macaroon_service)
        )
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        _extract_http_macaroon = pretend.call_recorder(lambda r: b"not a real macaroon")
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        permits = pretend.stub()
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits)
        )
        policy = security_policy.MacaroonAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), "upload")

        assert result == permits

    @pytest.mark.parametrize(
        "invalid_permission",
        ["admin", "moderator", "manage:user", "manage:project", "nonexistant"],
    )
    def test_denies_valid_macaroon_for_incorrect_permission(
        self, monkeypatch, invalid_permission
    ):
        macaroon_service = pretend.stub(
            verify=pretend.call_recorder(lambda *a: pretend.stub())
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda interface, **kw: macaroon_service)
        )
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        _extract_http_macaroon = pretend.call_recorder(lambda r: b"not a real macaroon")
        monkeypatch.setattr(
            security_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        permits = pretend.stub()
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits)
        )
        policy = security_policy.MacaroonAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), invalid_permission)

        assert result == Denied("")
        assert result.s == (
            f"API tokens are not valid for permission: {invalid_permission}!"
        )

    def test_principals_allowed_by_permission(self):
        principals = pretend.stub()
        backing_policy = pretend.stub(
            principals_allowed_by_permission=pretend.call_recorder(
                lambda *a: principals
            )
        )
        policy = security_policy.MacaroonAuthorizationPolicy(policy=backing_policy)

        assert (
            policy.principals_allowed_by_permission(pretend.stub(), pretend.stub())
            is principals
        )
