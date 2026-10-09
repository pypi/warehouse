# SPDX-License-Identifier: Apache-2.0

import base64
import types

import pytest

from pyramid.authorization import Allow
from pyramid.exceptions import HTTPForbidden
from pyramid.interfaces import ISecurityPolicy
from pyramid.testing import DummySecurityPolicy
from sqlalchemy import sql
from zope.interface.verify import verifyClass

from warehouse.accounts import UserContext, security_policy
from warehouse.accounts.models import DisableReason
from warehouse.ip_addresses.models import BanReason
from warehouse.predicates import AuthMethodsPredicate
from warehouse.sessions import Session
from warehouse.utils.security_policy import AuthenticationMethod

from ...common.db.accounts import UserFactory

UPLOAD_ROUTE = types.SimpleNamespace(
    name="forklift.legacy.file_upload",
    predicates=[AuthMethodsPredicate({"basic-auth", "macaroon"}, None)],
)


def _basic_auth(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


@pytest.fixture
def vary_spies(mocker):
    """
    Spy on the ``Vary`` callback a policy registers, returning a callable
    that asserts it was registered once for ``header`` on ``request``.
    """
    add_vary_cb = mocker.spy(security_policy, "add_vary_callback")

    def track(request):
        add_response_callback = mocker.spy(request, "add_response_callback")

        def assert_vary(header):
            add_vary_cb.assert_called_once_with(header)
            add_response_callback.assert_called_once_with(add_vary_cb.spy_return)

        return assert_vary

    return track


class TestBasicAuthSecurityPolicy:
    def test_verify(self):
        assert verifyClass(
            ISecurityPolicy,
            security_policy.BasicAuthSecurityPolicy,
        )

    def test_noops(self, mocker):
        """Basically, anything that isn't `identity()` is a no-op."""
        policy = security_policy.BasicAuthSecurityPolicy()
        with pytest.raises(NotImplementedError):
            policy.authenticated_userid(mocker.sentinel.request)
        with pytest.raises(NotImplementedError):
            policy.permits(
                mocker.sentinel.request,
                mocker.sentinel.context,
                mocker.sentinel.permission,
            )

        # These are no-ops, but they don't raise, used in MultiSecurityPolicy
        assert policy.forget(mocker.sentinel.request) == []
        assert policy.remember(mocker.sentinel.request, mocker.sentinel.userid) == []

    def test_identity_no_credentials(self, pyramid_request, vary_spies):
        assert_vary = vary_spies(pyramid_request)
        pyramid_request.matched_route = UPLOAD_ROUTE

        policy = security_policy.BasicAuthSecurityPolicy()

        assert policy.identity(pyramid_request) is None
        assert pyramid_request.authentication_method == AuthenticationMethod.BASIC_AUTH
        assert_vary("Authorization")

    def test_identity_credentials_fail(self, pyramid_request, vary_spies, mocker):
        assert_vary = vary_spies(pyramid_request)
        pyramid_request.matched_route = UPLOAD_ROUTE
        pyramid_request.headers["Authorization"] = _basic_auth("user", "password")
        pyramid_request.help_url = mocker.Mock(return_value="/help")

        policy = security_policy.BasicAuthSecurityPolicy()

        with pytest.raises(HTTPForbidden):
            policy.identity(pyramid_request)
        assert_vary("Authorization")

    @pytest.mark.parametrize(
        "matched_route",
        [None, types.SimpleNamespace(name="an.invalid.route", predicates=[])],
    )
    def test_invalid_request_fail(self, pyramid_request, matched_route):
        pyramid_request.matched_route = matched_route
        pyramid_request.headers["Authorization"] = _basic_auth("user", "password")

        policy = security_policy.BasicAuthSecurityPolicy()

        assert policy.identity(pyramid_request) is None

    def test_identity(self, pyramid_request, vary_spies):
        assert_vary = vary_spies(pyramid_request)
        pyramid_request.matched_route = UPLOAD_ROUTE
        pyramid_request.headers["Authorization"] = _basic_auth("__token__", "pypi-")

        policy = security_policy.BasicAuthSecurityPolicy()

        assert policy.identity(pyramid_request) is None
        assert pyramid_request.authentication_method == AuthenticationMethod.BASIC_AUTH
        assert_vary("Authorization")


class TestSessionSecurityPolicy:
    @pytest.fixture
    def session_request(self, db_request):
        db_request.session = Session()
        db_request.matched_route = types.SimpleNamespace(
            name="a.permitted.route", predicates=[]
        )
        return db_request

    @pytest.fixture
    def user(self, session_request):
        user = UserFactory.create(clear_pwd="password")
        session_request.session["auth.userid"] = str(user.id)
        return user

    def test_verify(self):
        assert verifyClass(
            ISecurityPolicy,
            security_policy.SessionSecurityPolicy,
        )

    def test_noops(self, mocker):
        policy = security_policy.SessionSecurityPolicy()
        with pytest.raises(NotImplementedError):
            policy.authenticated_userid(mocker.sentinel.request)

    def test_forget_and_remember(self, session_request, mocker):
        policy = security_policy.SessionSecurityPolicy()
        remember = mocker.spy(policy._session_helper, "remember")
        forget = mocker.spy(policy._session_helper, "forget")

        assert policy.remember(session_request, "some-user-id", foo=None) == []
        assert session_request.session["auth.userid"] == "some-user-id"
        remember.assert_called_once_with(session_request, "some-user-id", foo=None)

        assert policy.forget(session_request, foo=None) == []
        assert "auth.userid" not in session_request.session
        forget.assert_called_once_with(session_request, foo=None)

    @pytest.mark.usefixtures("user")
    def test_identity_missing_route(self, session_request, vary_spies):
        assert_vary = vary_spies(session_request)
        session_request.matched_route = None

        policy = security_policy.SessionSecurityPolicy()

        assert policy.identity(session_request) is None
        assert session_request.authentication_method == AuthenticationMethod.SESSION
        assert_vary("Cookie")

    @pytest.mark.parametrize(
        "route_name",
        [
            "api.echo",
            "api.simple.index",
        ],
    )
    @pytest.mark.usefixtures("user")
    def test_identity_skips_api_prefix_routes(
        self, session_request, vary_spies, route_name
    ):
        # api.* routes have no session middleware installed; skipping is an
        # infrastructure constraint, not a policy decision.
        assert_vary = vary_spies(session_request)
        session_request.matched_route = types.SimpleNamespace(name=route_name)

        policy = security_policy.SessionSecurityPolicy()

        assert policy.identity(session_request) is None
        assert session_request.authentication_method == AuthenticationMethod.SESSION
        assert_vary("Cookie")

    @pytest.mark.usefixtures("user")
    def test_identity_skips_when_auth_methods_excludes_session(
        self, session_request, vary_spies
    ):
        assert_vary = vary_spies(session_request)
        session_request.matched_route = UPLOAD_ROUTE

        policy = security_policy.SessionSecurityPolicy()

        assert policy.identity(session_request) is None
        assert session_request.authentication_method == AuthenticationMethod.SESSION
        assert_vary("Cookie")

    def test_identity_no_userid(self, session_request, vary_spies):
        assert_vary = vary_spies(session_request)

        policy = security_policy.SessionSecurityPolicy()

        assert policy.identity(session_request) is None
        assert session_request.authentication_method == AuthenticationMethod.SESSION
        assert session_request._unauthenticated_userid is None
        assert_vary("Cookie")

    def test_identity_no_user(self, session_request, user_service, vary_spies, mocker):
        assert_vary = vary_spies(session_request)
        get_user = mocker.spy(user_service, "get_user")
        userid = "00000000-0000-0000-0000-000000000000"
        session_request.session["auth.userid"] = userid

        policy = security_policy.SessionSecurityPolicy()

        assert policy.identity(session_request) is None
        assert session_request.authentication_method == AuthenticationMethod.SESSION
        assert session_request._unauthenticated_userid == userid
        get_user.assert_called_once_with(userid)
        assert_vary("Cookie")

    def test_identity_password_outdated(self, session_request, user, vary_spies):
        assert_vary = vary_spies(session_request)
        session_request.session.record_password_timestamp(0)

        policy = security_policy.SessionSecurityPolicy()

        assert policy.identity(session_request) is None
        assert session_request.authentication_method == AuthenticationMethod.SESSION
        assert "auth.userid" not in session_request.session
        assert session_request.session.peek_flash(queue="error") == [
            {"msg": "Session invalidated by password change", "safe": False}
        ]
        assert_vary("Cookie")

    @pytest.mark.parametrize(
        ("user_kwargs", "message"),
        [
            (
                {"is_frozen": True},
                (
                    "Your account has been suspended. "
                    "Please contact security@pypi.org for assistance."
                ),
            ),
            (
                {"password": "!", "disabled_for": DisableReason.CompromisedPassword},
                "Session invalidated",
            ),
        ],
    )
    def test_identity_is_disabled(
        self, session_request, user, vary_spies, user_kwargs, message
    ):
        assert_vary = vary_spies(session_request)
        for attr, value in user_kwargs.items():
            setattr(user, attr, value)
        # An outdated password would also invalidate the session; the disabled
        # message proves the disabled check runs first.
        session_request.session.record_password_timestamp(0)

        policy = security_policy.SessionSecurityPolicy()

        assert policy.identity(session_request) is None
        assert session_request.authentication_method == AuthenticationMethod.SESSION
        assert "auth.userid" not in session_request.session
        assert session_request.session.peek_flash(queue="error") == [
            {"msg": message, "safe": False}
        ]
        assert_vary("Cookie")

    def test_identity(self, session_request, user, user_service, vary_spies):
        assert_vary = vary_spies(session_request)
        session_request.session.record_password_timestamp(
            user_service.get_password_timestamp(user.id)
        )

        policy = security_policy.SessionSecurityPolicy()

        identity = policy.identity(session_request)
        assert identity.user is user
        assert identity.macaroon is None
        assert session_request.authentication_method == AuthenticationMethod.SESSION
        assert session_request.session["auth.userid"] == str(user.id)
        assert_vary("Cookie")

    @pytest.mark.usefixtures("user")
    def test_identity_ip_banned(
        self, session_request, user_service, vary_spies, mocker
    ):
        assert_vary = vary_spies(session_request)
        get_user = mocker.spy(user_service, "get_user")
        ip_address = session_request.ip_address
        ip_address.is_banned = True
        ip_address.ban_reason = BanReason.AUTHENTICATION_ATTEMPTS
        ip_address.ban_date = sql.func.now()

        policy = security_policy.SessionSecurityPolicy()

        assert policy.identity(session_request) is None
        assert session_request.authentication_method == AuthenticationMethod.SESSION
        assert session_request._unauthenticated_userid is None
        get_user.assert_not_called()
        assert_vary("Cookie")


@pytest.mark.parametrize(
    "policy_class",
    [security_policy.SessionSecurityPolicy],
)
class TestPermits:
    @pytest.fixture
    def permits(self, pyramid_config, pyramid_request, policy_class):
        """
        Check ``permission`` for ``user`` on a route named ``route``, against a
        context that grants ``myperm`` to ``allowed_user`` (``user`` by default).
        """

        def _permits(user, route, allowed_user=None):
            pyramid_config.set_security_policy(
                DummySecurityPolicy(identity=UserContext(user=user, macaroon=None))
            )
            pyramid_request.matched_route = route
            allowed_user = allowed_user or user
            context = types.SimpleNamespace(
                __acl__=[(Allow, f"user:{allowed_user.id}", "myperm")]
            )
            return policy_class().permits(pyramid_request, context, "myperm")

        return _permits

    @pytest.mark.parametrize("is_allowed_user", [True, False])
    def test_acl(self, permits, is_allowed_user):
        user = UserFactory.create(with_verified_primary_email=True)
        other = UserFactory.create()
        result = permits(
            user,
            types.SimpleNamespace(name="random.route"),
            allowed_user=user if is_allowed_user else other,
        )
        assert bool(result) == is_allowed_user

    def test_permits_with_unverified_email(self, permits):
        user = UserFactory.create()
        assert not permits(user, types.SimpleNamespace(name="manage.projects"))

    def test_permits_manage_projects_with_2fa(self, permits):
        user = UserFactory.create(with_verified_primary_email=True)
        assert permits(user, types.SimpleNamespace(name="manage.projects"))

    def test_deny_manage_projects_without_2fa(self, permits):
        user = UserFactory.create(with_verified_primary_email=True, totp_secret=None)
        assert not permits(user, types.SimpleNamespace(name="manage.projects"))

    def test_deny_forklift_file_upload_without_2fa(self, permits):
        user = UserFactory.create(with_verified_primary_email=True, totp_secret=None)
        assert not permits(user, UPLOAD_ROUTE)

    @pytest.mark.parametrize(
        "matched_route",
        [
            "manage.account",
            "manage.account.recovery-codes",
            "manage.account.totp-provision",
            "manage.account.two-factor",
            "manage.account.webauthn-provision",
            "manage.account.webauthn-provision.validate",
        ],
    )
    def test_permits_2fa_routes_without_2fa(self, permits, matched_route):
        user = UserFactory.create(with_verified_primary_email=True, totp_secret=None)
        assert permits(user, types.SimpleNamespace(name=matched_route))
