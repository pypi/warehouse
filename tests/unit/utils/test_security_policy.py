# SPDX-License-Identifier: Apache-2.0

import types

import pytest

from pyramid.interfaces import ISecurityPolicy
from pyramid.testing import DummySecurityPolicy
from zope.interface.verify import verifyClass

from tests.common.db.accounts import UserFactory
from warehouse.accounts.utils import UserContext
from warehouse.authnz import Permissions
from warehouse.utils import security_policy
from warehouse.utils.security_policy import (
    AuthenticationMethod,
    permission_allowed_by_authentication_method,
)


def test_principals_for():
    identity = types.SimpleNamespace()
    identity.__principals__ = lambda: ["a", "b", "z"]
    assert security_policy.principals_for(identity) == ["a", "b", "z"]


def test_principals_for_with_none():
    assert security_policy.principals_for(types.SimpleNamespace()) == []


class TestPermissionAllowedByAuthenticationMethod:
    @pytest.mark.parametrize(
        "permission",
        [
            Permissions.ProjectsUpload,
            # TODO: After danger-api sunset, move APIEcho and APIObservationsAdd
            #       to test_macaroon_disallowed_permissions (they'll be dropped
            #       from PERMISSION_AUTH_METHODS).
            Permissions.APIEcho,
            Permissions.APIObservationsAdd,
        ],
    )
    def test_macaroon_allowed_permissions(self, permission):
        assert permission_allowed_by_authentication_method(
            permission, AuthenticationMethod.MACAROON
        )

    @pytest.mark.parametrize(
        "permission",
        [
            Permissions.AccountManage,
            Permissions.ProjectsWrite,
            "nonexistent",
        ],
    )
    def test_macaroon_disallowed_permissions(self, permission):
        assert not permission_allowed_by_authentication_method(
            permission, AuthenticationMethod.MACAROON
        )

    def test_unknown_permission_defaults_to_session_only(self):
        assert permission_allowed_by_authentication_method(
            "nonexistent", AuthenticationMethod.SESSION
        )
        assert not permission_allowed_by_authentication_method(
            "nonexistent", AuthenticationMethod.MACAROON
        )
        assert not permission_allowed_by_authentication_method(
            "nonexistent", AuthenticationMethod.BASIC_AUTH
        )

    def test_session_permission_allows_session(self):
        assert permission_allowed_by_authentication_method(
            Permissions.AccountManage, AuthenticationMethod.SESSION
        )


def test_api_key_auth_method_placeholder_exists():
    # API_KEY is a placeholder for the dedicated API auth surface that
    # will replace danger-api's macaroon abuse. No policy implements it
    # yet; keeping it in the enum makes the PERMISSION_AUTH_METHODS table
    # and route predicates self-documenting about the migration target.
    assert AuthenticationMethod.API_KEY.value == "api-key"


class TestMultiSecurityPolicy:
    def test_verify(self):
        assert verifyClass(
            ISecurityPolicy,
            security_policy.MultiSecurityPolicy,
        )

    def test_reset(self, pyramid_request, mocker):
        identity1 = mocker.sentinel.identity1
        identity2 = mocker.sentinel.identity2
        identities = iter([identity1, identity2])

        subpolicies = [types.SimpleNamespace(identity=lambda r: next(identities))]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert policy.identity(pyramid_request) is identity1
        assert policy.identity(pyramid_request) is identity1

        policy.reset(pyramid_request)

        assert policy.identity(pyramid_request) is identity2

    def test_identity_none(self, pyramid_request):
        subpolicies = [DummySecurityPolicy(identity=None)]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert policy.identity(pyramid_request) is None

    def test_identity_first_come_first_serve(self, pyramid_request, mocker):
        identity1 = mocker.sentinel.identity1
        identity2 = mocker.sentinel.identity2
        subpolicies = [
            DummySecurityPolicy(identity=None),
            DummySecurityPolicy(identity=identity1),
            DummySecurityPolicy(identity=identity2),
        ]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert policy.identity(pyramid_request) is identity1

    def test_authenticated_userid_no_identity(self, pyramid_request):
        subpolicies = [DummySecurityPolicy(identity=None)]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert policy.authenticated_userid(pyramid_request) is None

    def test_authenticated_userid_nonuser_identity(self, db_request, mocker):
        nonuser = mocker.sentinel.nonuser
        subpolicies = [DummySecurityPolicy(identity=nonuser)]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert policy.authenticated_userid(db_request) is None

    def test_authenticated_userid_user_contex_macaroon(self, db_request, mocker):
        user = UserFactory.create()
        user_ctx = UserContext(user, mocker.sentinel.macaroon)

        subpolicies = [DummySecurityPolicy(identity=user_ctx)]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert (
            policy.authenticated_userid(db_request)
            == str(user.id)
            == str(user_ctx.user.id)
        )

    def test_authenticated_userid_user_context_no_macaroon(self, db_request):
        user = UserFactory.create()
        user_ctx = UserContext(user, None)

        subpolicies = [DummySecurityPolicy(identity=user_ctx)]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert policy.authenticated_userid(db_request) == str(user.id)

    def test_forget(self, mocker):
        subpolicies = [DummySecurityPolicy(forget_result=[("ForgetMe", "1")])]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        request = mocker.sentinel.request
        assert policy.forget(request, foo=None) == [("ForgetMe", "1")]

    def test_remember(self, mocker):
        subpolicies = [
            types.SimpleNamespace(
                remember=lambda r, uid, foo, **kw: [("RememberMe", foo)]
            )
        ]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        request = mocker.sentinel.request
        userid = mocker.sentinel.userid
        assert policy.remember(request, userid, foo="bob") == [("RememberMe", "bob")]

    def test_permits(self, pyramid_config, pyramid_request, mocker):
        identity1 = mocker.sentinel.identity1
        identity2 = mocker.sentinel.identity2
        context = mocker.sentinel.context

        subpolicies = [
            DummySecurityPolicy(identity=None),
            types.SimpleNamespace(
                identity=lambda r: identity1,
                permits=(
                    lambda r, c, p: (
                        r.identity == identity1 and c == context and p == "myperm"
                    )
                ),
            ),
            DummySecurityPolicy(identity=identity2),
        ]
        policy = security_policy.MultiSecurityPolicy(subpolicies)
        # Register the policy so request.identity resolves through it, exactly
        # as in production -- the permits() sanity check compares the two.
        pyramid_config.set_security_policy(policy)

        assert policy.permits(pyramid_request, context, "myperm")

    def test_permits_no_policy(self, pyramid_config, pyramid_request, mocker):
        subpolicies = [
            DummySecurityPolicy(identity=None),
            DummySecurityPolicy(identity=None),
            DummySecurityPolicy(identity=None),
        ]
        policy = security_policy.MultiSecurityPolicy(subpolicies)
        pyramid_config.set_security_policy(policy)
        context = mocker.sentinel.context

        assert not policy.permits(pyramid_request, context, "myperm")
