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
import pytest

from pyramid.interfaces import IAuthenticationPolicy, IAuthorizationPolicy
from pyramid.security import Denied
from zope.interface.verify import verifyClass

from warehouse.macaroons import auth_policy
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.services import InvalidMacaroon


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

    assert auth_policy._extract_http_macaroon(request) == result


@pytest.mark.parametrize(
    ["auth", "result"],
    [
        ("notbase64", None),
        ("bm90YXJlYWx0b2tlbg==", None),  # "notarealtoken"
        ("QGJhZHVzZXI6Zm9vYmFy", None),  # "@baduser:foobar"
        ("X190b2tlbl9fOmZvb2Jhcg==", "foobar"),  # "__token__:foobar"
    ],
)
def test_extract_basic_macaroon(auth, result):
    assert auth_policy._extract_basic_macaroon(auth) == result


class TestMacaroonAuthenticationPolicy:
    def test_verify(self):
        assert verifyClass(
            IAuthenticationPolicy, auth_policy.MacaroonAuthenticationPolicy
        )

    def test_unauthenticated_userid_invalid_macaroon(self, monkeypatch):
        _extract_http_macaroon = pretend.call_recorder(lambda r: None)
        monkeypatch.setattr(
            auth_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        policy = auth_policy.MacaroonAuthenticationPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(auth_policy, "add_vary_callback", add_vary_cb)

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None)
        )

        assert policy.unauthenticated_userid(request) is None
        assert _extract_http_macaroon.calls == [pretend.call(request)]
        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_unauthenticated_userid_valid_macaroon(self, monkeypatch):
        _extract_http_macaroon = pretend.call_recorder(lambda r: b"not a real macaroon")
        monkeypatch.setattr(
            auth_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        policy = auth_policy.MacaroonAuthenticationPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(auth_policy, "add_vary_callback", add_vary_cb)

        userid = uuid.uuid4()
        macaroon_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda macaroon: userid)
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(
                lambda interface, **kw: macaroon_service
            ),
            add_response_callback=pretend.call_recorder(lambda cb: None),
        )

        assert policy.unauthenticated_userid(request) == str(userid)
        assert _extract_http_macaroon.calls == [pretend.call(request)]
        assert request.find_service.calls == [
            pretend.call(IMacaroonService, context=None)
        ]
        assert macaroon_service.find_userid.calls == [
            pretend.call(b"not a real macaroon")
        ]
        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_unauthenticated_userid_valid_macaroon_invalid_userid(self, monkeypatch):
        _extract_http_macaroon = pretend.call_recorder(lambda r: b"not a real macaroon")
        monkeypatch.setattr(
            auth_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        policy = auth_policy.MacaroonAuthenticationPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(auth_policy, "add_vary_callback", add_vary_cb)

        macaroon_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda macaroon: None)
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(
                lambda interface, **kw: macaroon_service
            ),
            add_response_callback=pretend.call_recorder(lambda cb: None),
        )

        assert policy.unauthenticated_userid(request) is None
        assert _extract_http_macaroon.calls == [pretend.call(request)]
        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert macaroon_service.find_userid.calls == [
            pretend.call(b"not a real macaroon")
        ]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_remember(self):
        policy = auth_policy.MacaroonAuthenticationPolicy()
        assert policy.remember(pretend.stub(), pretend.stub()) == []

    def test_forget(self):
        policy = auth_policy.MacaroonAuthenticationPolicy()
        assert policy.forget(pretend.stub()) == []


class TestMacaroonAuthorizationPolicy:
    def test_verify(self):
        assert verifyClass(
            IAuthorizationPolicy, auth_policy.MacaroonAuthorizationPolicy
        )

    def test_permits_no_active_request(self, monkeypatch):
        get_current_request = pretend.call_recorder(lambda: None)
        monkeypatch.setattr(auth_policy, "get_current_request", get_current_request)

        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: pretend.stub())
        )
        policy = auth_policy.MacaroonAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == Denied("There was no active request.")

    def test_permits_no_macaroon(self, monkeypatch):
        request = pretend.stub()
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(auth_policy, "get_current_request", get_current_request)

        _extract_http_macaroon = pretend.call_recorder(lambda r: None)
        monkeypatch.setattr(
            auth_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        permits = pretend.stub()
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits)
        )
        policy = auth_policy.MacaroonAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == permits

    def test_permits_invalid_macaroon(self, monkeypatch):
        macaroon_service = pretend.stub(verify=pretend.raiser(InvalidMacaroon("foo")))
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda interface, **kw: macaroon_service)
        )
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(auth_policy, "get_current_request", get_current_request)

        _extract_http_macaroon = pretend.call_recorder(lambda r: b"not a real macaroon")
        monkeypatch.setattr(
            auth_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        permits = pretend.stub()
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits)
        )
        policy = auth_policy.MacaroonAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == Denied("The supplied token was invalid: foo")

    def test_permits_valid_macaroon(self, monkeypatch):
        macaroon_service = pretend.stub(
            verify=pretend.call_recorder(lambda *a: pretend.stub())
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda interface, **kw: macaroon_service)
        )
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(auth_policy, "get_current_request", get_current_request)

        _extract_http_macaroon = pretend.call_recorder(lambda r: b"not a real macaroon")
        monkeypatch.setattr(
            auth_policy, "_extract_http_macaroon", _extract_http_macaroon
        )

        permits = pretend.stub()
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits)
        )
        policy = auth_policy.MacaroonAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == permits

    def test_principals_allowed_by_permission(self):
        principals = pretend.stub()
        backing_policy = pretend.stub(
            principals_allowed_by_permission=pretend.call_recorder(
                lambda *a: principals
            )
        )
        policy = auth_policy.MacaroonAuthorizationPolicy(policy=backing_policy)

        assert (
            policy.principals_allowed_by_permission(pretend.stub(), pretend.stub())
            is principals
        )
