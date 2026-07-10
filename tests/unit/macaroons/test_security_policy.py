# SPDX-License-Identifier: Apache-2.0

import types

import pytest

from pyramid.authorization import Allow
from pyramid.interfaces import ISecurityPolicy
from pyramid.security import Denied
from pyramid.testing import DummySecurityPolicy
from zope.interface.verify import verifyClass

from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.utils import UserContext
from warehouse.authnz import Permissions
from warehouse.macaroons import security_policy
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.services import InvalidMacaroonError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.utils import PublisherTokenContext

from ...common.db.accounts import UserFactory
from ...common.db.macaroons import MacaroonFactory


@pytest.mark.parametrize(
    ("auth", "result"),
    [
        (None, None),
        ("notarealtoken", None),
        ("maybeafuturemethod foobar", None),
        ("token foobar", "foobar"),
        ("bearer foobar", "foobar"),
        ("basic X190b2tlbl9fOmZvb2Jhcg==", "foobar"),  # "__token__:foobar"
    ],
)
def test_extract_http_macaroon(auth, result, pyramid_request):
    if auth is not None:
        pyramid_request.headers["Authorization"] = auth

    assert security_policy._extract_http_macaroon(pyramid_request) == result


@pytest.mark.parametrize(
    ("auth", "result"),
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

    def test_noops(self, mocker):
        policy = security_policy.MacaroonSecurityPolicy()
        with pytest.raises(NotImplementedError):
            policy.authenticated_userid(mocker.sentinel.request)

    def test_forget_and_remember(self, mocker):
        policy = security_policy.MacaroonSecurityPolicy()

        assert policy.forget(mocker.sentinel.request) == []
        assert policy.remember(mocker.sentinel.request, mocker.sentinel.userid) == []

    def test_identity_no_http_macaroon(self, pyramid_request, mocker):
        policy = security_policy.MacaroonSecurityPolicy()

        add_vary_cb = mocker.spy(security_policy, "add_vary_callback")
        extract_http_macaroon = mocker.patch.object(
            security_policy, "_extract_http_macaroon", autospec=True, return_value=None
        )
        add_response_callback = mocker.spy(pyramid_request, "add_response_callback")

        assert policy.identity(pyramid_request) is None
        extract_http_macaroon.assert_called_once_with(pyramid_request)

        add_vary_cb.assert_called_once_with("Authorization")
        add_response_callback.assert_called_once_with(add_vary_cb.spy_return)

    def test_identity_no_db_macaroon(self, pyramid_request, macaroon_service, mocker):
        policy = security_policy.MacaroonSecurityPolicy()

        add_vary_cb = mocker.spy(security_policy, "add_vary_callback")
        extract_http_macaroon = mocker.patch.object(
            security_policy,
            "_extract_http_macaroon",
            autospec=True,
            return_value=mocker.sentinel.raw_macaroon,
        )
        mocker.patch.object(
            macaroon_service,
            "find_from_raw",
            autospec=True,
            side_effect=InvalidMacaroonError,
        )
        find_service = mocker.spy(pyramid_request, "find_service")
        add_response_callback = mocker.spy(pyramid_request, "add_response_callback")

        assert policy.identity(pyramid_request) is None
        extract_http_macaroon.assert_called_once_with(pyramid_request)
        find_service.assert_called_once_with(IMacaroonService, context=None)
        macaroon_service.find_from_raw.assert_called_once_with(
            mocker.sentinel.raw_macaroon
        )

        add_vary_cb.assert_called_once_with("Authorization")
        add_response_callback.assert_called_once_with(add_vary_cb.spy_return)

    def test_identity_disabled_user(
        self, pyramid_request, macaroon_service, user_service, mocker
    ):
        policy = security_policy.MacaroonSecurityPolicy()

        add_vary_cb = mocker.spy(security_policy, "add_vary_callback")
        extract_http_macaroon = mocker.patch.object(
            security_policy,
            "_extract_http_macaroon",
            autospec=True,
            return_value=mocker.sentinel.raw_macaroon,
        )

        user = UserFactory.build(id="deadbeef-dead-beef-deadbeef-dead")
        macaroon = MacaroonFactory.build(user=user, oidc_publisher=None)
        mocker.patch.object(
            macaroon_service, "find_from_raw", autospec=True, return_value=macaroon
        )
        mocker.patch.object(
            user_service, "is_disabled", autospec=True, return_value=(True, Exception)
        )

        find_service = mocker.spy(pyramid_request, "find_service")
        add_response_callback = mocker.spy(pyramid_request, "add_response_callback")

        assert policy.identity(pyramid_request) is None
        extract_http_macaroon.assert_called_once_with(pyramid_request)
        assert find_service.call_args_list == [
            mocker.call(IMacaroonService, context=None),
            mocker.call(IUserService, context=None),
        ]
        macaroon_service.find_from_raw.assert_called_once_with(
            mocker.sentinel.raw_macaroon
        )
        user_service.is_disabled.assert_called_once_with(
            "deadbeef-dead-beef-deadbeef-dead"
        )

        add_vary_cb.assert_called_once_with("Authorization")
        add_response_callback.assert_called_once_with(add_vary_cb.spy_return)

    def test_identity_user(
        self, pyramid_request, macaroon_service, user_service, mocker
    ):
        policy = security_policy.MacaroonSecurityPolicy()

        add_vary_cb = mocker.spy(security_policy, "add_vary_callback")
        extract_http_macaroon = mocker.patch.object(
            security_policy,
            "_extract_http_macaroon",
            autospec=True,
            return_value=mocker.sentinel.raw_macaroon,
        )

        user = UserFactory.build(id="deadbeef-dead-beef-deadbeef-dead")
        macaroon = MacaroonFactory.build(user=user, oidc_publisher=None)
        mocker.patch.object(
            macaroon_service, "find_from_raw", autospec=True, return_value=macaroon
        )
        mocker.patch.object(
            user_service, "is_disabled", autospec=True, return_value=(False, Exception)
        )

        find_service = mocker.spy(pyramid_request, "find_service")
        add_response_callback = mocker.spy(pyramid_request, "add_response_callback")

        assert policy.identity(pyramid_request) == UserContext(user, macaroon)
        extract_http_macaroon.assert_called_once_with(pyramid_request)
        assert find_service.call_args_list == [
            mocker.call(IMacaroonService, context=None),
            mocker.call(IUserService, context=None),
        ]
        macaroon_service.find_from_raw.assert_called_once_with(
            mocker.sentinel.raw_macaroon
        )
        user_service.is_disabled.assert_called_once_with(
            "deadbeef-dead-beef-deadbeef-dead"
        )

        add_vary_cb.assert_called_once_with("Authorization")
        add_response_callback.assert_called_once_with(add_vary_cb.spy_return)

    def test_identity_oidc_publisher(self, pyramid_request, macaroon_service, mocker):
        policy = security_policy.MacaroonSecurityPolicy()

        add_vary_cb = mocker.spy(security_policy, "add_vary_callback")
        extract_http_macaroon = mocker.patch.object(
            security_policy,
            "_extract_http_macaroon",
            autospec=True,
            return_value=mocker.sentinel.raw_macaroon,
        )

        oidc_publisher = mocker.sentinel.oidc_publisher
        oidc_additional = {"oidc": {"foo": "bar"}}
        macaroon = MacaroonFactory.build(
            user=None, oidc_publisher=oidc_publisher, additional=oidc_additional
        )
        mocker.patch.object(
            macaroon_service, "find_from_raw", autospec=True, return_value=macaroon
        )

        find_service = mocker.spy(pyramid_request, "find_service")
        add_response_callback = mocker.spy(pyramid_request, "add_response_callback")

        identity = policy.identity(pyramid_request)
        assert identity
        assert identity.publisher is oidc_publisher
        assert identity == PublisherTokenContext(
            oidc_publisher, SignedClaims(oidc_additional["oidc"])
        )

        extract_http_macaroon.assert_called_once_with(pyramid_request)
        assert find_service.call_args_list == [
            mocker.call(IMacaroonService, context=None),
            mocker.call(IUserService, context=None),
        ]
        macaroon_service.find_from_raw.assert_called_once_with(
            mocker.sentinel.raw_macaroon
        )

        add_vary_cb.assert_called_once_with("Authorization")
        add_response_callback.assert_called_once_with(add_vary_cb.spy_return)

    def test_permits_invalid_macaroon(self, pyramid_request, macaroon_service, mocker):
        mocker.patch.object(
            macaroon_service,
            "verify",
            autospec=True,
            side_effect=InvalidMacaroonError("foo"),
        )
        mocker.patch.object(
            security_policy,
            "_extract_http_macaroon",
            autospec=True,
            return_value="not a real macaroon",
        )

        policy = security_policy.MacaroonSecurityPolicy()
        result = policy.permits(
            pyramid_request, mocker.sentinel.context, Permissions.ProjectsUpload
        )

        assert result == Denied("")
        assert result.s == "Invalid API Token: foo"

    @pytest.mark.parametrize(
        ("principals", "expected"), [(["user:5"], True), (["user:1"], False)]
    )
    def test_permits_valid_macaroon(
        self,
        pyramid_request,
        pyramid_config,
        macaroon_service,
        mocker,
        principals,
        expected,
    ):
        mocker.patch.object(
            macaroon_service,
            "verify",
            autospec=True,
            return_value=mocker.sentinel.verified,
        )
        mocker.patch.object(
            security_policy,
            "_extract_http_macaroon",
            autospec=True,
            return_value="not a real macaroon",
        )

        identity = types.SimpleNamespace(__principals__=lambda: principals)
        pyramid_config.set_security_policy(DummySecurityPolicy(identity=identity))

        context = types.SimpleNamespace(
            __acl__=[(Allow, "user:5", [Permissions.ProjectsUpload])]
        )

        policy = security_policy.MacaroonSecurityPolicy()
        result = policy.permits(pyramid_request, context, Permissions.ProjectsUpload)

        assert bool(result) == expected

    @pytest.mark.parametrize(
        "invalid_permission",
        [Permissions.AccountManage, Permissions.ProjectsWrite, "nonexistent"],
    )
    def test_denies_valid_macaroon_for_incorrect_permission(
        self, mocker, invalid_permission
    ):
        mocker.patch.object(
            security_policy,
            "_extract_http_macaroon",
            autospec=True,
            return_value="not a real macaroon",
        )

        policy = security_policy.MacaroonSecurityPolicy()
        result = policy.permits(
            mocker.sentinel.request, mocker.sentinel.context, invalid_permission
        )

        assert result == Denied("")
        assert result.s == (
            f"API tokens are not valid for permission: {invalid_permission}!"
        )
