# SPDX-License-Identifier: Apache-2.0

import datetime
import types

import pytest

from pyramid.httpexceptions import HTTPUnauthorized
from pyramid.interfaces import ISecurityPolicy
from pyramid.security import Allowed
from pyramid.testing import DummySecurityPolicy
from zope.interface.verify import verifyClass

from warehouse.accounts.security_policy import (
    BasicAuthSecurityPolicy,
    SessionSecurityPolicy,
)
from warehouse.api.maintainer import ApiKeyScope, _security_policy as security_policy
from warehouse.api.maintainer._services import generate_api_key, hash_api_key
from warehouse.api.maintainer._utils import ApiKeyContext
from warehouse.authnz import Permissions
from warehouse.macaroons.security_policy import MacaroonSecurityPolicy
from warehouse.predicates import AuthMethodsPredicate
from warehouse.utils.security_policy import (
    PERMISSION_AUTH_METHODS,
    AuthenticationMethod,
    MultiSecurityPolicy,
)

from ....common.db.accounts import UserFactory
from ....common.db.maintainer_api import ApiKeyFactory
from ....common.db.packaging import ProjectFactory, RoleFactory


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
        pytest.param("Bearer pypi-AgEIcHlwaS5vcmc", None, id="upload token"),
        pytest.param("Bearer pypi_mapi_v1_abc", "pypi_mapi_v1_abc", id="bearer"),
        pytest.param("bearer pypi_mapi_v1_abc", "pypi_mapi_v1_abc", id="lowercase"),
        pytest.param("token pypi_mapi_v1_abc", None, id="token scheme"),
    ],
)
def test_extract_api_key(pyramid_request, authorization, expected):
    if authorization is not None:
        pyramid_request.headers["Authorization"] = authorization

    assert security_policy._extract_api_key(pyramid_request) == expected


def test_permission_scopes_need_api_key_auth():
    """Every permission with a scope must also be grantable by an API key."""
    for permission in security_policy.PERMISSION_SCOPES:
        assert AuthenticationMethod.API_KEY in PERMISSION_AUTH_METHODS[permission]


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
        pyramid_request.headers["Authorization"] = f"Bearer {generate_api_key()}"
        verify = mocker.spy(api_key_service, "verify")
        add_vary_cb = mocker.spy(security_policy, "add_vary_callback")
        add_response_callback = mocker.spy(pyramid_request, "add_response_callback")

        assert policy.identity(pyramid_request) is None
        verify.assert_not_called()
        add_vary_cb.assert_called_once_with("Authorization")
        add_response_callback.assert_called_once_with(add_vary_cb.spy_return)

    def test_identity_rejects_upload_token(
        self, pyramid_request, api_key_service, mocker
    ):
        """A macaroon never reaches the API key service."""
        policy = security_policy.ApiKeySecurityPolicy()
        pyramid_request.matched_route = _route("api-key")
        pyramid_request.headers["Authorization"] = "Bearer pypi-AgEIcHlwaS5vcmc"
        verify = mocker.spy(api_key_service, "verify")

        assert policy.identity(pyramid_request) is None
        verify.assert_not_called()

    @pytest.mark.parametrize(
        "api_key_kwargs",
        [
            pytest.param(None, id="unknown"),
            pytest.param({"revoked": datetime.datetime.now()}, id="revoked"),
        ],
    )
    def test_identity_invalid_key(self, db_request, api_key_kwargs):
        policy = security_policy.ApiKeySecurityPolicy()
        db_request.matched_route = _route("api-key")
        raw_key = generate_api_key()
        if api_key_kwargs is not None:
            ApiKeyFactory.create(hashed_key=hash_api_key(raw_key), **api_key_kwargs)
        db_request.headers["Authorization"] = f"Bearer {raw_key}"

        assert policy.identity(db_request) is None
        assert db_request.authentication_method == AuthenticationMethod.API_KEY

    def test_identity_expired_key(self, db_request):
        """An expired key says so, instead of falling through to a bare 403."""
        policy = security_policy.ApiKeySecurityPolicy()
        db_request.matched_route = _route("api-key")
        raw_key = generate_api_key()
        expires = datetime.datetime(2026, 1, 1)
        ApiKeyFactory.create(hashed_key=hash_api_key(raw_key), expires=expires)
        db_request.headers["Authorization"] = f"Bearer {raw_key}"

        with pytest.raises(HTTPUnauthorized) as excinfo:
            policy.identity(db_request)

        assert excinfo.value.headers["WWW-Authenticate"] == (
            'Bearer error="invalid_token", '
            'error_description="API key expired at 2026-01-01T00:00:00"'
        )

    def test_identity_disabled_user(self, db_request, api_key_service, mocker):
        """A frozen user's key is rejected and its use is not recorded."""
        policy = security_policy.ApiKeySecurityPolicy()
        db_request.matched_route = _route("api-key")
        user = UserFactory.create(clear_pwd="password", is_frozen=True)
        raw_key, _ = api_key_service.create_api_key(
            user.id,
            "ci",
            [ApiKeyScope.ProjectReleasesYank],
            datetime.datetime.now() + datetime.timedelta(days=30),
        )
        db_request.headers["Authorization"] = f"Bearer {raw_key}"
        record_use = mocker.spy(api_key_service, "record_use")

        assert policy.identity(db_request) is None
        record_use.assert_not_called()

    def test_identity(self, db_request, api_key_service, mocker):
        policy = security_policy.ApiKeySecurityPolicy()
        db_request.matched_route = _route("api-key")
        user = UserFactory.create(clear_pwd="password")
        raw_key, api_key = api_key_service.create_api_key(
            user.id,
            "ci",
            [ApiKeyScope.ProjectReleasesYank],
            datetime.datetime.now() + datetime.timedelta(days=30),
        )
        db_request.headers["Authorization"] = f"Bearer {raw_key}"
        record_use = mocker.spy(api_key_service, "record_use")

        assert policy.identity(db_request) == ApiKeyContext(user=user, api_key=api_key)
        assert db_request.authentication_method == AuthenticationMethod.API_KEY
        record_use.assert_called_once_with(api_key.id)

    def test_permits_wrong_auth_method(self, db_request, pyramid_config):
        policy = security_policy.ApiKeySecurityPolicy()
        api_key = ApiKeyFactory.create()
        pyramid_config.set_security_policy(
            DummySecurityPolicy(
                identity=ApiKeyContext(user=api_key.user, api_key=api_key)
            )
        )

        result = policy.permits(db_request, None, Permissions.ProjectsUpload)

        assert not result
        assert result.reason == "invalid_permission"

    def test_permits_missing_scope(self, db_request, pyramid_config):
        policy = security_policy.ApiKeySecurityPolicy()
        api_key = ApiKeyFactory.create(scopes=[])
        pyramid_config.set_security_policy(
            DummySecurityPolicy(
                identity=ApiKeyContext(user=api_key.user, api_key=api_key)
            )
        )

        result = policy.permits(db_request, None, Permissions.ProjectsYank)

        assert not result
        assert result.reason == "insufficient_scope"

    def test_permits_unmapped_permission(self, db_request, pyramid_config, monkeypatch):
        """A permission API keys may grant, but with no scope, is denied."""
        monkeypatch.setitem(
            PERMISSION_AUTH_METHODS,
            Permissions.APIEcho,
            frozenset({AuthenticationMethod.API_KEY}),
        )
        policy = security_policy.ApiKeySecurityPolicy()
        api_key = ApiKeyFactory.create()
        pyramid_config.set_security_policy(
            DummySecurityPolicy(
                identity=ApiKeyContext(user=api_key.user, api_key=api_key)
            )
        )

        result = policy.permits(db_request, None, Permissions.APIEcho)

        assert not result
        assert result.reason == "invalid_permission"

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
    def test_permits_account_requirements(
        self, db_request, pyramid_config, user_kwargs, reason
    ):
        """An Owner's key is still denied until the account is set up."""
        policy = security_policy.ApiKeySecurityPolicy()
        api_key = ApiKeyFactory.create(user=UserFactory.create(**user_kwargs))
        project = ProjectFactory.create()
        RoleFactory.create(user=api_key.user, project=project, role_name="Owner")
        pyramid_config.set_security_policy(
            DummySecurityPolicy(
                identity=ApiKeyContext(user=api_key.user, api_key=api_key)
            )
        )

        result = policy.permits(db_request, project, Permissions.ProjectsYank)

        assert not result
        assert result.reason == reason

    @pytest.mark.parametrize(
        ("role_name", "allowed"),
        [("Owner", True), ("Maintainer", False), (None, False)],
    )
    def test_permits_checks_acl(self, db_request, pyramid_config, role_name, allowed):
        policy = security_policy.ApiKeySecurityPolicy()
        api_key = ApiKeyFactory.create(
            user=UserFactory.create(with_verified_primary_email=True)
        )
        project = ProjectFactory.create()
        if role_name is not None:
            RoleFactory.create(user=api_key.user, project=project, role_name=role_name)
        pyramid_config.set_security_policy(
            DummySecurityPolicy(
                identity=ApiKeyContext(user=api_key.user, api_key=api_key)
            )
        )

        result = policy.permits(db_request, project, Permissions.ProjectsYank)

        assert bool(result) is allowed


class TestRoundTrip:
    @pytest.fixture
    def policy(self):
        return MultiSecurityPolicy(
            [
                SessionSecurityPolicy(),
                BasicAuthSecurityPolicy(),
                MacaroonSecurityPolicy(),
                security_policy.ApiKeySecurityPolicy(),
            ]
        )

    def test_generate_verify_authorize(
        self, db_request, pyramid_config, api_key_service, policy
    ):
        user = UserFactory.create(
            clear_pwd="password", with_verified_primary_email=True
        )
        project = ProjectFactory.create()
        RoleFactory.create(user=user, project=project, role_name="Owner")
        raw_key, api_key = api_key_service.create_api_key(
            user.id,
            "ci",
            [ApiKeyScope.ProjectReleasesYank],
            datetime.datetime.now() + datetime.timedelta(days=30),
        )
        db_request.matched_route = _route("api-key")
        db_request.headers["Authorization"] = f"Bearer {raw_key}"
        pyramid_config.set_security_policy(policy)

        assert db_request.identity == ApiKeyContext(user=user, api_key=api_key)
        assert isinstance(
            policy.permits(db_request, project, Permissions.ProjectsYank), Allowed
        )

    def test_api_key_rejected_on_macaroon_route(
        self, db_request, api_key_service, macaroon_service, policy, mocker
    ):
        """An API key on an upload-token route never reaches either service."""
        api_key_verify = mocker.spy(api_key_service, "verify")
        macaroon_verify = mocker.spy(macaroon_service, "verify_signature_only")
        db_request.matched_route = _route("macaroon")
        db_request.headers["Authorization"] = f"Bearer {generate_api_key()}"

        assert policy.identity(db_request) is None
        api_key_verify.assert_not_called()
        macaroon_verify.assert_not_called()
