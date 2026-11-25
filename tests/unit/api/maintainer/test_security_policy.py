# SPDX-License-Identifier: Apache-2.0

import datetime as dt
import types

import pytest

from pyramid.exceptions import PredicateMismatch
from pyramid.httpexceptions import HTTPForbidden
from pyramid.interfaces import ISecurityPolicy
from pyramid.testing import DummySecurityPolicy
from zope.interface.verify import verifyClass

from warehouse.api.maintainer import (
    SCOPE_PERMISSIONS,
    ApiKeyContext,
    ApiKeyScope,
    _authz,
    _bearer,
    generate_api_key,
    security_policy,
)
from warehouse.authnz import Permissions
from warehouse.config import RootFactory
from warehouse.errors import WarehouseDenied
from warehouse.predicates import AuthMethodsPredicate
from warehouse.utils import now
from warehouse.utils.security_policy import (
    PERMISSION_AUTH_METHODS,
    AuthenticationMethod,
)

from ....common.db.accounts import UserFactory
from ....common.db.maintainer_api import ApiKeyFactory


def _route(*auth_methods):
    return types.SimpleNamespace(
        name="api.maintainer.test",
        predicates=[AuthMethodsPredicate(set(auth_methods), None)],
    )


@pytest.mark.parametrize(
    ("authorization", "expected"),
    [
        pytest.param(None, None, id="no header"),
        pytest.param("Bearer", None, id="no credential"),
        pytest.param("Basic pypi_mapi_v1_abc", None, id="not bearer"),
        pytest.param("Bearer pypi-AgEIcHlwaS5vcmc", None, id="API token"),
        pytest.param("Bearer pypi_mapi_v1_abc", "pypi_mapi_v1_abc", id="bearer"),
        pytest.param("bearer pypi_mapi_v1_abc", "pypi_mapi_v1_abc", id="lowercase"),
        pytest.param("Bearer  pypi_mapi_v1_abc\t", "pypi_mapi_v1_abc", id="whitespace"),
    ],
)
def test_extract_api_key(pyramid_request, authorization, expected):
    if authorization is not None:
        pyramid_request.headers["Authorization"] = authorization

    assert security_policy._extract_api_key(pyramid_request) == expected


@pytest.fixture
def echo_scope_for_anyone(monkeypatch):
    """Let any signed-in user hold test:echo, so the resource ACL decides."""
    monkeypatch.setitem(
        SCOPE_PERMISSIONS,
        ApiKeyScope.TestEcho,
        Permissions.AccountManage,
    )


def _with_identity(pyramid_config, api_key):
    pyramid_config.set_security_policy(
        DummySecurityPolicy(identity=ApiKeyContext(user=api_key.user, api_key=api_key))
    )


def _in_days(days):
    return now() + dt.timedelta(days=days)


class TestApiKeySecurityPolicy:
    def test_verify(self):
        assert verifyClass(ISecurityPolicy, security_policy.ApiKeySecurityPolicy)

    def test_noops(self, mocker):
        policy = security_policy.ApiKeySecurityPolicy()

        assert policy.forget(mocker.sentinel.request) == []
        assert policy.remember(mocker.sentinel.request, mocker.sentinel.userid) == []
        with pytest.raises(NotImplementedError):
            policy.authenticated_userid(mocker.sentinel.request)

    @pytest.mark.parametrize(
        "matched_route",
        [
            pytest.param(None, id="no matched route"),
            pytest.param(
                types.SimpleNamespace(name="api.test", predicates=[]),
                id="no auth_methods declared",
            ),
            pytest.param(_route("macaroon"), id="auth_methods excludes api-key"),
        ],
    )
    def test_identity_route_not_opted_in(
        self, pyramid_request, api_key_service, mocker, matched_route
    ):
        policy = security_policy.ApiKeySecurityPolicy()
        pyramid_request.matched_route = matched_route
        pyramid_request.authentication_method = mocker.sentinel.unchanged
        pyramid_request.headers["Authorization"] = f"Bearer {generate_api_key()}"
        verify = mocker.spy(api_key_service, "verify")

        assert policy.identity(pyramid_request) is None
        verify.assert_not_called()
        assert pyramid_request.authentication_method is mocker.sentinel.unchanged

    def test_identity_varies_on_authorization(self, pyramid_request, mocker):
        policy = security_policy.ApiKeySecurityPolicy()
        pyramid_request.matched_route = _route("api-key")
        add_vary_cb = mocker.spy(security_policy, "add_vary_callback")

        assert policy.identity(pyramid_request) is None
        add_vary_cb.assert_called_once_with("Authorization")

    def test_identity_banned_ip(self, db_request, api_key_service, mocker):
        policy = security_policy.ApiKeySecurityPolicy()
        db_request.matched_route = _route("api-key")
        db_request.headers["Authorization"] = f"Bearer {generate_api_key()}"
        mocker.patch.object(
            db_request.banned, "by_ip", autospec=True, return_value=True
        )
        verify = mocker.spy(api_key_service, "verify")

        assert policy.identity(db_request) is None
        verify.assert_not_called()
        assert not hasattr(db_request, "api_key_rejection")

    def test_identity_invalid_key(self, db_request):
        """The service's reason is kept for the error response."""
        policy = security_policy.ApiKeySecurityPolicy()
        db_request.matched_route = _route("api-key")
        raw_key = generate_api_key()
        ApiKeyFactory.create(raw_key=raw_key, expires=dt.datetime(2026, 1, 1))
        db_request.headers["Authorization"] = f"Bearer {raw_key}"

        assert policy.identity(db_request) is None
        assert db_request.authentication_method == AuthenticationMethod.API_KEY
        assert db_request.api_key_rejection == (
            "Maintainer API key expired at 2026-01-01T00:00:00Z"
        )

    def test_identity_disabled_user(self, db_request, api_key_service):
        policy = security_policy.ApiKeySecurityPolicy()
        db_request.matched_route = _route("api-key")
        user = UserFactory.create(clear_pwd="password", is_frozen=True)
        raw_key, _ = api_key_service.create_api_key(
            user, "ci", [ApiKeyScope.TestEcho], _in_days(30)
        )
        db_request.headers["Authorization"] = f"Bearer {raw_key}"

        assert policy.identity(db_request) is None

    def test_identity(self, db_request, api_key_service, mocker):
        """Use is recorded in permits(), once the request is allowed."""
        policy = security_policy.ApiKeySecurityPolicy()
        db_request.matched_route = _route("api-key")
        user = UserFactory.create(clear_pwd="password")
        raw_key, api_key = api_key_service.create_api_key(
            user, "ci", [ApiKeyScope.TestEcho], _in_days(30)
        )
        db_request.headers["Authorization"] = f"Bearer {raw_key}"
        record_use = mocker.spy(api_key_service, "record_use")

        assert policy.identity(db_request) == ApiKeyContext(user=user, api_key=api_key)
        assert db_request.authentication_method == AuthenticationMethod.API_KEY
        record_use.assert_not_called()

    def test_permits_wrong_auth_method(self, db_request, pyramid_config):
        policy = security_policy.ApiKeySecurityPolicy()
        _with_identity(pyramid_config, ApiKeyFactory.create())

        result = policy.permits(db_request, None, Permissions.ProjectsUpload)

        assert not result
        assert result.reason == "invalid_permission"

    def test_permits_missing_scope(self, db_request, pyramid_config):
        policy = security_policy.ApiKeySecurityPolicy()
        _with_identity(pyramid_config, ApiKeyFactory.create(scopes=[]))

        result = policy.permits(
            db_request, RootFactory(db_request), Permissions.APIEcho
        )

        assert isinstance(result, _authz.InsufficientScope)
        assert result.scope == ApiKeyScope.TestEcho

    def test_permits_unmapped_permission(self, db_request, pyramid_config, monkeypatch):
        """A permission API keys may grant, but with no scope, is denied."""
        monkeypatch.setitem(
            PERMISSION_AUTH_METHODS,
            Permissions.APIObservationsAdd,
            frozenset({AuthenticationMethod.API_KEY}),
        )
        policy = security_policy.ApiKeySecurityPolicy()
        _with_identity(pyramid_config, ApiKeyFactory.create())

        result = policy.permits(db_request, None, Permissions.APIObservationsAdd)

        assert not result
        assert result.reason == "invalid_permission"

    @pytest.mark.parametrize(
        ("is_superuser", "allowed"), [(True, True), (False, False)]
    )
    def test_permits_scope_permission(
        self, db_request, pyramid_config, api_key_service, mocker, is_superuser, allowed
    ):
        """A test: scope works only while its owner holds APIKeyScopesTest."""
        policy = security_policy.ApiKeySecurityPolicy()
        user = UserFactory.create(
            is_superuser=is_superuser, with_verified_primary_email=True
        )
        api_key = ApiKeyFactory.create(user=user)
        _with_identity(pyramid_config, api_key)
        record_use = mocker.spy(api_key_service, "record_use")
        root = RootFactory(db_request)

        result = policy.permits(db_request, root, Permissions.APIEcho)

        assert bool(result) is allowed
        if allowed:
            # Recorded once per request, however many checks pass.
            assert policy.permits(db_request, root, Permissions.APIEcho)
            record_use.assert_called_once_with(api_key.id)
        else:
            # A plain denial: the key has the scope, the account changed.
            assert not isinstance(result, _authz.InsufficientScope)
            assert result.reason == "scope_not_permitted"
            record_use.assert_not_called()

    @pytest.mark.parametrize(
        ("user_kwargs", "reason"),
        [
            pytest.param(
                {"with_verified_primary_email": False},
                "unverified_email",
                id="unverified email",
            ),
            pytest.param(
                {"with_verified_primary_email": True, "totp_secret": None},
                "2fa_required",
                id="no 2fa",
            ),
        ],
    )
    @pytest.mark.usefixtures("echo_scope_for_anyone")
    def test_permits_account_requirements(
        self, db_request, pyramid_config, user_kwargs, reason
    ):
        """A key the ACL would allow is still denied until the account is set up."""
        policy = security_policy.ApiKeySecurityPolicy()
        user = UserFactory.create(is_observer=True, **user_kwargs)
        _with_identity(pyramid_config, ApiKeyFactory.create(user=user))

        result = policy.permits(
            db_request, RootFactory(db_request), Permissions.APIEcho
        )

        assert not result
        assert result.reason == reason

    @pytest.mark.parametrize("is_observer", [True, False])
    @pytest.mark.usefixtures("echo_scope_for_anyone")
    def test_permits_checks_acl(self, db_request, pyramid_config, is_observer):
        """With the scope and its permission held, the resource ACL decides."""
        policy = security_policy.ApiKeySecurityPolicy()
        user = UserFactory.create(
            is_observer=is_observer, with_verified_primary_email=True
        )
        _with_identity(pyramid_config, ApiKeyFactory.create(user=user))

        result = policy.permits(
            db_request, RootFactory(db_request), Permissions.APIEcho
        )

        assert bool(result) is is_observer


class TestBearerChallenge:
    def _request(self, pyramid_request, mocker, *, identity=None, authorization=None):
        mocker.patch.object(type(pyramid_request), "identity", identity)
        pyramid_request.matched_route = _route("api-key")
        if authorization is not None:
            pyramid_request.headers["Authorization"] = authorization
        return pyramid_request

    def test_invalid_token(self, pyramid_request, mocker):
        request = self._request(
            pyramid_request, mocker, authorization="Bearer pypi_mapi_v1_x"
        )
        request.api_key_rejection = "Maintainer API key expired at 2026-01-01T00:00:00Z"

        resp = security_policy.bearer_challenge(HTTPForbidden(), request)

        assert resp.status_code == 401
        assert resp.content_type == "application/problem+json"
        assert resp.json_body == {
            "title": "Unauthorized",
            "status": 401,
            "detail": request.api_key_rejection,
        }
        assert resp.headers["WWW-Authenticate"] == (
            'Bearer error="invalid_token", '
            'error_description="Maintainer API key expired at 2026-01-01T00:00:00Z"'
        )

    def test_insufficient_scope(self, pyramid_request, mocker):
        identity = ApiKeyContext(mocker.sentinel.user, mocker.sentinel.api_key)
        request = self._request(pyramid_request, mocker, identity=identity)
        denied = _authz.InsufficientScope(
            "Maintainer API key lacks the required scope: test:echo",
            scope=ApiKeyScope.TestEcho,
        )

        resp = security_policy.bearer_challenge(HTTPForbidden(result=denied), request)

        assert resp.status_code == 403
        assert resp.json_body["title"] == "Forbidden"
        assert resp.json_body["detail"] == denied.msg
        assert resp.headers["WWW-Authenticate"] == (
            'Bearer error="insufficient_scope", '
            f'error_description="{denied.msg}", scope="test:echo"'
        )

    def test_other_policy_denial(self, pyramid_request, mocker):
        """A valid key denied for, say, missing 2FA is told so."""
        identity = ApiKeyContext(mocker.sentinel.user, mocker.sentinel.api_key)
        request = self._request(pyramid_request, mocker, identity=identity)
        denied = WarehouseDenied("Enable 2FA.", reason="2fa_required")

        resp = security_policy.bearer_challenge(HTTPForbidden(result=denied), request)

        assert resp.status_code == 403
        assert resp.json_body["detail"] == "Enable 2FA."
        assert resp.headers["WWW-Authenticate"] == "Bearer"

    def test_api_key_acl_denial(self, pyramid_request, mocker):
        """An ACL denial names principals, so the detail stays generic."""
        request = self._request(
            pyramid_request, mocker, identity=ApiKeyContext(None, None)
        )

        resp = security_policy.bearer_challenge(HTTPForbidden(), request)

        assert resp.status_code == 403
        assert resp.json_body["detail"] == "Access was denied to this resource."
        assert resp.headers["WWW-Authenticate"] == "Bearer"

    def test_other_identity(self, pyramid_request, mocker):
        request = self._request(pyramid_request, mocker, identity=object())

        assert security_policy.bearer_challenge(HTTPForbidden(), request) is None

    def test_rejected_without_reason(self, pyramid_request, mocker):
        """A banned IP or disabled owner leaves no reason: plain 403, no oracle."""
        request = self._request(
            pyramid_request, mocker, authorization=f"Bearer {generate_api_key()}"
        )

        assert security_policy.bearer_challenge(HTTPForbidden(), request) is None

    def test_predicate_mismatch(self, pyramid_request, mocker):
        request = self._request(pyramid_request, mocker)

        assert (
            security_policy.bearer_challenge(PredicateMismatch("accept"), request)
            is None
        )

    @pytest.mark.parametrize(
        "authorization",
        [
            pytest.param(None, id="none"),
            pytest.param("Bearer pypi-AgEIcHlwaS5vcmc", id="API token"),
            pytest.param("Token pypi_mapi_v1_abc", id="wrong scheme"),
        ],
    )
    def test_no_api_key_on_api_key_route(self, pyramid_request, mocker, authorization):
        """A bare challenge, with no error code."""
        request = self._request(pyramid_request, mocker, authorization=authorization)

        resp = security_policy.bearer_challenge(HTTPForbidden(), request)

        assert resp.status_code == 401
        assert resp.headers["WWW-Authenticate"] == "Bearer"
        assert resp.json_body["detail"].startswith("Send a Maintainer API key")

    def test_shared_route_keeps_its_responses(self, pyramid_request, mocker):
        """A route API tokens also open keeps its answers for those clients."""
        request = self._request(pyramid_request, mocker)
        request.matched_route = _route("macaroon", "api-key")

        assert security_policy.bearer_challenge(HTTPForbidden(), request) is None

    def test_challenge_drops_unquotable_characters(self):
        assert _bearer.challenge(error_description='a "b" \\c\u00e9\n') == (
            'Bearer error_description="a b c"'
        )

    def test_route_without_api_keys(self, pyramid_request, mocker):
        request = self._request(pyramid_request, mocker)
        request.matched_route = _route("macaroon")

        assert security_policy.bearer_challenge(HTTPForbidden(), request) is None
