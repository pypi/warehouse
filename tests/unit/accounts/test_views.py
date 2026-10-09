# SPDX-License-Identifier: Apache-2.0

import datetime
import json
import uuid

from types import SimpleNamespace

import freezegun
import pretend
import pytest

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPMovedPermanently,
    HTTPNotFound,
    HTTPSeeOther,
    HTTPTooManyRequests,
    HTTPUnauthorized,
)
from pyramid.interfaces import ISecurityPolicy
from webauthn.authentication.verify_authentication_response import (
    VerifiedAuthentication,
)
from webauthn.helpers import bytes_to_base64url
from webob.multidict import MultiDict

from warehouse.accounts import views
from warehouse.accounts.forms import (
    LoginForm,
    RecoveryCodeAuthenticationForm,
    RegistrationForm,
    RequestPasswordResetForm,
    ResetPasswordForm,
    TOTPAuthenticationForm,
)
from warehouse.accounts.interfaces import (
    IDomainStatusService,
    IPasswordBreachedService,
    ITokenService,
    IUserService,
    TokenException,
    TokenExpired,
    TokenInvalid,
    TokenMissing,
    TooManyEmailsAdded,
    TooManyFailedLogins,
    TooManyPasswordResetRequests,
)
from warehouse.accounts.models import (
    TermsOfServiceEngagement,
    UniqueLoginStatus,
    UserUniqueLogin,
)
from warehouse.accounts.services import NullPasswordBreachedService, TokenService
from warehouse.accounts.views import (
    REMEMBER_DEVICE_COOKIE,
    two_factor_and_totp_validate,
)
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.captcha.interfaces import ICaptchaService
from warehouse.events.tags import EventTag
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.interfaces import TooManyOIDCRegistrations
from warehouse.oidc.models import (
    PendingActiveStatePublisher,
    PendingGitHubPublisher,
    PendingGitLabPublisher,
    PendingGooglePublisher,
)
from warehouse.organizations.models import (
    OrganizationInvitation,
    OrganizationRole,
    OrganizationRoleType,
)
from warehouse.packaging.interfaces import IProjectService
from warehouse.packaging.models import Role, RoleInvitation
from warehouse.rate_limiting import DummyRateLimiter
from warehouse.rate_limiting.interfaces import IRateLimiter
from warehouse.sessions import Session
from warehouse.utils.security_policy import MultiSecurityPolicy

from ...common.db.accounts import (
    EmailFactory,
    RecoveryCodeFactory,
    UserFactory,
    UserUniqueLoginFactory,
    WebAuthnFactory,
)
from ...common.db.ip_addresses import IpAddressFactory
from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationRoleFactory,
)
from ...common.db.packaging import (
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
    RoleInvitationFactory,
)


class TestFailedLoginView:
    def test_too_many_failed_logins(self, pyramid_request):
        exc = TooManyFailedLogins(resets_in=datetime.timedelta(seconds=600))

        resp = views.failed_logins(exc, pyramid_request)

        assert resp.status == "429 Too Many Failed Login Attempts"
        assert resp.detail == (
            "There have been too many unsuccessful login attempts. "
            "You have been locked out for 10 minutes. "
            "Please try again later."
        )
        assert dict(resp.headers).get("Retry-After") == "600"

    def test_too_many_emails_added(self, pyramid_request):
        exc = TooManyEmailsAdded(resets_in=datetime.timedelta(seconds=600))

        resp = views.unverified_emails(exc, pyramid_request)

        assert resp.status == "429 Too Many Requests"
        assert resp.detail == (
            "Too many emails have been added to this account without verifying "
            "them. Check your inbox and follow the verification links. (IP: "
            f"{pyramid_request.remote_addr})"
        )
        assert dict(resp.headers).get("Retry-After") == "600"

    def test_too_many_password_reset_requests(self, pyramid_request):
        exc = TooManyPasswordResetRequests(resets_in=datetime.timedelta(seconds=600))

        resp = views.incomplete_password_resets(exc, pyramid_request)

        assert resp.status == "429 Too Many Requests"
        assert resp.detail == (
            "Too many password resets have been requested for this account without "
            "completing them. Check your inbox and follow the verification links. (IP: "
            f"{pyramid_request.remote_addr})"
        )
        assert dict(resp.headers).get("Retry-After") == "600"


class TestUserProfile:
    def test_user_redirects_username(self, db_request, mocker):
        user = UserFactory.create()

        mocker.patch.object(
            db_request,
            "current_route_path",
            autospec=True,
            return_value="/user/the-redirect/",
        )
        # Intentionally swap the case of the username to trigger the redirect
        db_request.matchdict = {"username": user.username.swapcase()}

        result = views.profile(user, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/user/the-redirect/"
        db_request.current_route_path.assert_called_once_with(username=user.username)

    def test_returns_user(self, db_request):
        user = UserFactory.create()
        assert views.profile(user, db_request) == {
            "user": user,
            "live_projects": [],
            "archived_projects": [],
        }

    def test_user_profile_queries_once_for_all_projects(
        self, db_request, query_recorder
    ):
        user = UserFactory.create()
        projects = ProjectFactory.create_batch(3)
        for project in projects:
            # associate the user to each project as role: owner
            RoleFactory.create(user=user, project=project)
            # Add some releases, with time skew to ensure the ordering is correct
            ReleaseFactory.create(
                project=project, created=project.created + datetime.timedelta(minutes=1)
            )
            ReleaseFactory.create(
                project=project, created=project.created + datetime.timedelta(minutes=2)
            )
            # Add a prerelease, shouldn't affect any results
            ReleaseFactory.create(
                project=project,
                created=project.created + datetime.timedelta(minutes=3),
                is_prerelease=True,
            )
        # add one more project, associated to the user, but no releases
        RoleFactory.create(user=user, project=ProjectFactory.create())

        with query_recorder:
            response = views.profile(user, db_request)

        assert response["user"] == user
        assert len(response["live_projects"]) == 3
        # Two queries, one for the user (via context), one for their projects
        assert len(query_recorder.queries) == 2

    def test_returns_archived_projects(self, db_request):
        user = UserFactory.create()

        projects = ProjectFactory.create_batch(3)
        for project in projects:
            RoleFactory.create(user=user, project=project)
            ReleaseFactory.create(project=project)

        archived_project = ProjectFactory.create(lifecycle_status="archived")
        RoleFactory.create(user=user, project=archived_project)
        ReleaseFactory.create(project=archived_project)

        resp = views.profile(user, db_request)

        assert len(resp["live_projects"]) == 3
        assert len(resp["archived_projects"]) == 1


@pytest.fixture
def auth_token_services(pyramid_services):
    """
    Register a real ``TokenService`` per login token name, each with its own
    salt as in production, so a token read under the wrong name fails.
    """
    services = {
        name: TokenService(secret="secret", salt=name, max_age=21600)
        for name in ("two_factor", "remember_device", "confirm_login")
    }
    for name, service in services.items():
        pyramid_services.register_service(service, ITokenService, None, name=name)
    return services


@pytest.fixture
def two_factor_token_service(auth_token_services):
    return auth_token_services["two_factor"]


@pytest.fixture
def remember_device_token_service(auth_token_services):
    return auth_token_services["remember_device"]


@pytest.fixture
def two_factor_user(db_session):
    """
    A TOTP-enabled user whose last login predates any token signed in the test.
    """
    return UserFactory.create(
        last_login=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
    )


@pytest.fixture
def breach_service(pyramid_services):
    service = NullPasswordBreachedService()
    pyramid_services.register_service(service, IPasswordBreachedService, None)
    return service


@pytest.fixture
def password_reset_token(token_service):
    """Sign a password-reset token for ``user`` with the real token service."""

    def _make(user, *, last_login=None, password_date=None):
        return token_service.dumps(
            {
                "action": "password-reset",
                "user.id": user.id,
                "user.last_login": (
                    user.last_login if last_login is None else last_login
                ),
                "user.password_date": (
                    user.password_date if password_date is None else password_date
                ),
            }
        )

    return _make


class TestAccountsSearch:
    def test_unauthenticated_raises_401(self, pyramid_request):
        with pytest.raises(HTTPUnauthorized):
            views.accounts_search(pyramid_request)

    def test_no_query_string_raises_400(self, pyramid_request):
        pyramid_request.user = UserFactory.build()
        pyramid_request.params = MultiDict({})
        with pytest.raises(HTTPBadRequest):
            views.accounts_search(pyramid_request)

    def test_returns_users_with_prefix(
        self, db_request, pyramid_services, ratelimit_service
    ):
        foo = UserFactory.create(username="foo")
        bas = [
            UserFactory.create(username="bar"),
            UserFactory.create(username="baz"),
        ]

        db_request.user = foo
        pyramid_services.register_service(
            ratelimit_service, IRateLimiter, None, name="accounts.search"
        )

        db_request.params = MultiDict({"username": "f"})
        result = views.accounts_search(db_request)
        assert result == {"users": [foo]}

        db_request.params = MultiDict({"username": "ba"})
        result = views.accounts_search(db_request)
        assert result == {"users": bas}

        db_request.params = MultiDict({"username": "zzz"})
        with pytest.raises(HTTPNotFound):
            views.accounts_search(db_request)

    def test_when_rate_limited(
        self, db_request, pyramid_services, user_service, mocker
    ):
        search_limiter = DummyRateLimiter()
        mocker.patch.object(search_limiter, "test", autospec=True, return_value=False)
        pyramid_services.register_service(
            search_limiter, IRateLimiter, None, name="accounts.search"
        )
        mocker.spy(user_service, "get_users_by_prefix")
        db_request.user = UserFactory.build()

        db_request.params = MultiDict({"username": "foo"})
        result = views.accounts_search(db_request)

        search_limiter.test.assert_called_once_with(db_request.ip_address)
        user_service.get_users_by_prefix.assert_not_called()
        assert result == {"users": []}


class TestLogin:
    @pytest.fixture
    def form_class(self, mocker):
        return mocker.create_autospec(LoginForm)

    @pytest.fixture
    def valid_form(self, form_class):
        form_class.return_value.validate.return_value = True
        return form_class.return_value

    @pytest.mark.parametrize("next_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_form(
        self, pyramid_request, user_service, breach_service, form_class, next_url
    ):
        if next_url is not None:
            pyramid_request.GET["next"] = next_url

        result = views.login(pyramid_request, _form_class=form_class)

        assert result == {
            "form": form_class.return_value,
            "redirect": {"field": "next", "data": next_url},
        }
        form_class.assert_called_once_with(
            pyramid_request.POST,
            request=pyramid_request,
            user_service=user_service,
            breach_service=breach_service,
            check_password_metrics_tags=["method:auth", "auth_method:login_form"],
        )

    @pytest.mark.parametrize("next_url", [None, "/foo/bar/", "/wat/"])
    def test_post_invalid_returns_form(
        self,
        pyramid_request,
        user_service,
        breach_service,
        form_class,
        metrics,
        next_url,
    ):
        pyramid_request.method = "POST"
        if next_url is not None:
            pyramid_request.POST["next"] = next_url
        form_obj = form_class.return_value
        form_obj.validate.return_value = False

        result = views.login(pyramid_request, _form_class=form_class)
        metrics.increment.assert_not_called()

        assert result == {
            "form": form_obj,
            "redirect": {"field": "next", "data": next_url},
        }
        form_class.assert_called_once_with(
            pyramid_request.POST,
            request=pyramid_request,
            user_service=user_service,
            breach_service=breach_service,
            check_password_metrics_tags=["method:auth", "auth_method:login_form"],
        )
        form_obj.validate.assert_called_once_with()

    @pytest.mark.parametrize("with_user", [True, False])
    def test_post_validate_redirects(
        self,
        db_request,
        user_service,
        breach_service,
        form_class,
        valid_form,
        metrics,
        with_user,
        mocker,
    ):
        remember = mocker.patch.object(
            views, "remember", autospec=True, return_value=[]
        )

        user = UserFactory.create(
            totp_secret=None, with_terms_of_service_agreement=True
        )
        mocker.patch.object(user, "record_event", autospec=True, return_value=None)
        mocker.spy(user_service, "find_userid")
        mocker.spy(user_service, "update_user")

        db_request.method = "POST"
        db_request.session = Session({"a": "b", "foo": "bar"})
        for method in ("invalidate", "new_csrf_token", "record_auth_timestamp"):
            mocker.spy(db_request.session, method)

        db_request._unauthenticated_userid = str(uuid.uuid4()) if with_user else None

        db_request.registry.settings = {
            "sessions.secret": "dummy_secret",
            "terms.revision": "initial",
        }

        valid_form.username.data = user.username

        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/the-redirect"
        )

        now = datetime.datetime.now(datetime.UTC)

        with freezegun.freeze_time(now):
            result = views.login(db_request, _form_class=form_class)

        metrics.increment.assert_not_called()

        assert isinstance(result, HTTPSeeOther)
        db_request.route_path.assert_called_once_with("manage.projects")
        assert result.headers["Location"] == "/the-redirect"
        assert result.headers["Set-Cookie"].startswith("user_id__insecure=")

        form_class.assert_called_once_with(
            db_request.POST,
            request=db_request,
            user_service=user_service,
            breach_service=breach_service,
            check_password_metrics_tags=["method:auth", "auth_method:login_form"],
        )
        valid_form.validate.assert_called_once_with()

        user_service.find_userid.assert_called_once_with(user.username)
        user_service.update_user.assert_called_once_with(user.id, last_login=now)
        user.record_event.assert_called_once_with(
            tag=EventTag.Account.LoginSuccess,
            request=db_request,
            additional={"two_factor_method": None, "two_factor_label": None},
        )

        kept_session = {
            key: value
            for key, value in db_request.session.items()
            if key in ("a", "foo")
        }
        if with_user:
            assert kept_session == {}
        else:
            assert kept_session == {"a": "b", "foo": "bar"}

        remember.assert_called_once_with(db_request, str(user.id))
        db_request.session.invalidate.assert_called_once_with()
        db_request.session.new_csrf_token.assert_called_once_with()
        db_request.session.record_auth_timestamp.assert_called_once_with()

    def test_post_validate_flash_tos(
        self, db_request, user_service, breach_service, form_class, valid_form, mocker
    ):
        user = UserFactory.create(totp_secret=None)
        mocker.patch.object(user, "record_event", autospec=True, return_value=None)
        mocker.spy(user_service, "record_tos_engagement")

        db_request.method = "POST"
        db_request.session = Session()
        mocker.spy(db_request.session, "flash")
        db_request.registry.settings = {"terms.revision": "the-revision"}

        valid_form.username.data = user.username
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/the-redirect"
        )

        views.login(db_request, _form_class=form_class)

        db_request.session.flash.assert_called_once_with(
            ('Please review our updated <a href="/the-redirect">Terms of Service</a>.'),
            safe=True,
        )
        user_service.record_tos_engagement.assert_called_once_with(
            user.id, "the-revision", TermsOfServiceEngagement.Flashed
        )

    @pytest.mark.parametrize(
        # The set of all possible next URLs. Since this set is infinite, we
        # test only a finite set of reasonable URLs.
        ("expected_next_url", "observed_next_url"),
        [("/security/", "/security/"), ("http://example.com", "/the-redirect")],
    )
    def test_post_validate_no_redirects(
        self,
        db_request,
        pyramid_config,
        breach_service,
        form_class,
        valid_form,
        expected_next_url,
        observed_next_url,
        mocker,
    ):
        user = UserFactory.create(
            totp_secret=None, with_terms_of_service_agreement=True
        )
        mocker.patch.object(user, "record_event", autospec=True, return_value=None)

        db_request.method = "POST"
        db_request.POST["next"] = expected_next_url
        db_request.session = Session()
        db_request.registry.settings = {"terms.revision": "initial"}
        mocker.spy(db_request.session, "record_auth_timestamp")

        security_policy = MultiSecurityPolicy([])
        mocker.spy(security_policy, "reset")
        pyramid_config.set_security_policy(security_policy)

        valid_form.username.data = user.username
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/the-redirect"
        )

        result = views.login(db_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == observed_next_url
        user.record_event.assert_called_once_with(
            tag=EventTag.Account.LoginSuccess,
            request=db_request,
            additional={"two_factor_method": None, "two_factor_label": None},
        )
        db_request.session.record_auth_timestamp.assert_called_once_with()
        security_policy.reset.assert_called_once_with(db_request)

    def test_redirect_authenticated_user(self, pyramid_request, mocker):
        pyramid_request.user = UserFactory.build()
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="/the-redirect"
        )
        result = views.login(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    @pytest.mark.parametrize("redirect_url", ["test_redirect_url", None])
    def test_two_factor_auth(
        self,
        db_request,
        two_factor_token_service,
        breach_service,
        form_class,
        valid_form,
        redirect_url,
        mocker,
    ):
        user = UserFactory.create()
        mocker.spy(two_factor_token_service, "dumps")

        db_request.method = "POST"
        if redirect_url:
            db_request.POST["next"] = redirect_url

        valid_form.username.data = user.username
        mocker.patch.object(
            db_request,
            "route_path",
            autospec=True,
            return_value="/account/two-factor",
        )
        result = views.login(db_request, _form_class=form_class)

        token_expected_data = {"userid": user.id}
        if redirect_url:
            token_expected_data["redirect_to"] = redirect_url

        two_factor_token_service.dumps.assert_called_once_with(token_expected_data)
        db_request.route_path.assert_called_once_with(
            "accounts.two-factor", _query=two_factor_token_service.dumps.spy_return
        )
        assert isinstance(result, HTTPSeeOther)
        assert result.headerlist == [
            ("Content-Type", "text/html; charset=UTF-8"),
            ("Content-Length", "0"),
            ("Location", "/account/two-factor"),
        ]

    def test_login_with_remembered_device_confirms_unique_login(
        self,
        db_request,
        remember_device_token_service,
        breach_service,
        form_class,
        valid_form,
        mocker,
    ):
        mocker.patch.object(
            views, "remember", autospec=True, return_value=[("foo", "bar")]
        )

        user = UserFactory.create(with_terms_of_service_agreement=True)
        mocker.patch.object(user, "record_event", autospec=True, return_value=None)

        UserUniqueLoginFactory.create(
            user=user,
            ip_address=db_request.ip_address,
            status=UniqueLoginStatus.PENDING,
        )

        db_request.cookies[REMEMBER_DEVICE_COOKIE] = (
            remember_device_token_service.dumps({"user_id": user.id})
        )
        db_request.method = "POST"
        db_request.session = Session()
        db_request.registry.settings = {
            "sessions.secret": "dummy_secret",
            "terms.revision": "initial",
        }

        valid_form.username.data = user.username
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/the-redirect"
        )

        views.login(db_request, _form_class=form_class)

        unique_login = (
            db_request.db.query(UserUniqueLogin)
            .filter(UserUniqueLogin.user == user)
            .one()
        )
        assert unique_login.status == UniqueLoginStatus.CONFIRMED

    def test_login_updates_last_used(
        self, db_request, breach_service, form_class, valid_form, mocker
    ):
        mocker.patch.object(
            views, "remember", autospec=True, return_value=[("foo", "bar")]
        )

        user = UserFactory.create(
            totp_secret=None, with_terms_of_service_agreement=True
        )
        mocker.patch.object(user, "record_event", autospec=True, return_value=None)

        # Create a unique login with a timestamp in the distant past.
        past_timestamp = datetime.datetime(1970, 1, 1)
        UserUniqueLoginFactory.create(
            user=user,
            ip_address=db_request.ip_address,
            status=UniqueLoginStatus.CONFIRMED,
            last_used=past_timestamp,
        )

        db_request.method = "POST"
        db_request.session = Session()
        db_request.registry.settings = {
            "sessions.secret": "dummy_secret",
            "terms.revision": "initial",
        }

        valid_form.username.data = user.username
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/the-redirect"
        )

        # Simulate the login.
        views.login(db_request, _form_class=form_class)

        unique_login = db_request.db.query(UserUniqueLogin).one()
        assert unique_login.last_used > past_timestamp


class TestTwoFactor:
    @pytest.fixture
    def form_class(self, mocker):
        return mocker.create_autospec(TOTPAuthenticationForm)

    def test_get_two_factor_data_invalid_after_login(
        self, db_request, two_factor_token_service
    ):
        sign_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=30)
        user = UserFactory.create(
            last_login=datetime.datetime.now(datetime.UTC)
            - datetime.timedelta(seconds=1)
        )

        with freezegun.freeze_time(sign_time):
            db_request.query_string = two_factor_token_service.dumps(
                {"userid": user.id}
            )

        with pytest.raises(TokenInvalid):
            views._get_two_factor_data(db_request)

    def test_two_factor_and_totp_validate_redirect_to_account_login(
        self,
        db_request,
        two_factor_token_service,
        mocker,
    ):
        """
        Checks redirect to the login page if the 2fa login got expired.

        Given there's user in the database and has a token signed before last_login date
        When the user calls accounts.two-factor view
        Then the user is redirected to account/login page

        ... warning::
            This test has to use database and load the user from database
            to make sure we always compare user.last_login as timezone-aware datetime.

        """
        user = UserFactory.create(
            username="jdoe",
            name="Joe",
            password="any",
            is_active=True,
            last_login=datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(days=+1),
        )
        token_data = {"userid": user.id}

        # Remove user object from scope, The `token_service` will load the user
        # from the `user_service` and handle it from there
        db_request.db.expunge(user)
        del user

        token = two_factor_token_service.dumps(token_data)
        db_request.query_string = token
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/account/login/"
        )

        two_factor_and_totp_validate(db_request)
        # This view is redirected to only during a TokenException recovery
        # which is called in two instances:
        # 1. No userid in token
        # 2. The token has expired
        db_request.route_path.assert_called_once_with("accounts.login")

    @pytest.mark.parametrize("redirect_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_totp_form(
        self,
        db_request,
        two_factor_token_service,
        user_service,
        two_factor_user,
        form_class,
        redirect_url,
        mocker,
    ):
        query_params = {"userid": two_factor_user.id}
        if redirect_url:
            query_params["redirect_to"] = redirect_url

        db_request.query_string = two_factor_token_service.dumps(query_params)
        mocker.spy(two_factor_token_service, "loads")
        db_request.registry.settings = {"remember_device.days": 30}

        result = views.two_factor_and_totp_validate(db_request, _form_class=form_class)

        two_factor_token_service.loads.assert_called_once_with(
            db_request.query_string, return_timestamp=True
        )
        assert result == {
            "totp_form": form_class.return_value,
            "remember_device_days": 30,
        }
        form_class.assert_called_once_with(
            db_request.POST,
            request=db_request,
            user_id=str(two_factor_user.id),
            user_service=user_service,
            check_password_metrics_tags=["method:auth", "auth_method:login_form"],
        )

    @pytest.mark.parametrize("redirect_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_webauthn(
        self,
        db_request,
        two_factor_token_service,
        two_factor_user,
        form_class,
        redirect_url,
        mocker,
    ):
        two_factor_user.totp_secret = None
        WebAuthnFactory.create(user=two_factor_user)
        query_params = {"userid": two_factor_user.id}
        if redirect_url:
            query_params["redirect_to"] = redirect_url

        db_request.query_string = two_factor_token_service.dumps(query_params)
        mocker.spy(two_factor_token_service, "loads")
        db_request.registry.settings = {"remember_device.days": 30}

        result = views.two_factor_and_totp_validate(db_request, _form_class=form_class)

        two_factor_token_service.loads.assert_called_once_with(
            db_request.query_string, return_timestamp=True
        )
        assert result == {"has_webauthn": True, "remember_device_days": 30}
        form_class.assert_not_called()

    @pytest.mark.parametrize("redirect_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_recovery_code_status(
        self,
        db_request,
        two_factor_token_service,
        two_factor_user,
        form_class,
        redirect_url,
        mocker,
    ):
        two_factor_user.totp_secret = None
        RecoveryCodeFactory.create(user=two_factor_user)
        query_params = {"userid": two_factor_user.id}
        if redirect_url:
            query_params["redirect_to"] = redirect_url

        db_request.query_string = two_factor_token_service.dumps(query_params)
        mocker.spy(two_factor_token_service, "loads")
        db_request.registry.settings = {"remember_device.days": 30}

        result = views.two_factor_and_totp_validate(db_request, _form_class=form_class)

        two_factor_token_service.loads.assert_called_once_with(
            db_request.query_string, return_timestamp=True
        )
        assert result == {"has_recovery_codes": True, "remember_device_days": 30}
        form_class.assert_not_called()

    @pytest.mark.parametrize("redirect_url", ["/test_redirect_url", None])
    @pytest.mark.parametrize("has_recovery_codes", [True, False])
    @pytest.mark.parametrize("remember_device", [True, False])
    def test_totp_auth(
        self,
        db_request,
        two_factor_token_service,
        form_class,
        redirect_url,
        has_recovery_codes,
        remember_device,
        mocker,
    ):
        remember = mocker.patch.object(
            views, "remember", autospec=True, return_value=[("foo", "bar")]
        )
        _remember_device = mocker.patch.object(views, "_remember_device", autospec=True)
        send_email = mocker.patch.object(
            views, "send_recovery_code_reminder_email", autospec=True
        )

        user = UserFactory.create(
            with_verified_primary_email=True,
            with_terms_of_service_agreement=True,
            username="testuser",
            name="Test User",
            last_login=(
                datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
            ),
        )
        if has_recovery_codes:
            RecoveryCodeFactory.create(user=user)
        # A confirmed login from this IP makes the device known.
        UserUniqueLoginFactory.create(
            user=user,
            ip_address=db_request.ip_address,
            status=UniqueLoginStatus.CONFIRMED,
        )
        mocker.patch.object(user, "record_event", autospec=True, return_value=None)

        query_params = {"userid": user.id}
        if redirect_url:
            query_params["redirect_to"] = redirect_url
        db_request.query_string = two_factor_token_service.dumps(query_params)

        db_request.method = "POST"
        db_request.session = Session({"a": "b", "foo": "bar"})
        for method in ("invalidate", "new_csrf_token", "record_auth_timestamp"):
            mocker.spy(db_request.session, method)
        db_request.registry.settings = {
            "remember_device.days": 30,
            "terms.revision": "initial",
        }

        form_obj = form_class.return_value
        form_obj.validate.return_value = True
        form_obj.totp_value.data = "test-otp-secret"
        form_obj.remember_device.data = remember_device
        db_request.user = user

        result = views.two_factor_and_totp_validate(db_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == (redirect_url or "/")

        remember.assert_called_once_with(db_request, str(user.id))
        db_request.session.invalidate.assert_called_once_with()
        db_request.session.new_csrf_token.assert_called_once_with()
        user.record_event.assert_called_once_with(
            tag=EventTag.Account.LoginSuccess,
            request=db_request,
            additional={"two_factor_method": "totp", "two_factor_label": "totp"},
        )
        db_request.session.record_auth_timestamp.assert_called_once_with()
        if has_recovery_codes:
            send_email.assert_not_called()
        else:
            send_email.assert_called_once_with(db_request, user)

        if remember_device:
            _remember_device.assert_called_once_with(
                db_request, result, str(user.id), "totp"
            )
        else:
            _remember_device.assert_not_called()

    def test_totp_auth_already_authed(self, pyramid_request, pyramid_config, mocker):
        pyramid_config.testing_securitypolicy(identity=UserFactory.build())
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="redirect_to"
        )

        result = views.two_factor_and_totp_validate(pyramid_request)

        pyramid_request.route_path.assert_called_once_with("manage.projects")

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "redirect_to"

    def test_totp_form_invalid(
        self, db_request, two_factor_token_service, two_factor_user, form_class, mocker
    ):
        db_request.query_string = two_factor_token_service.dumps(
            {"userid": two_factor_user.id}
        )
        mocker.spy(two_factor_token_service, "loads")
        db_request.method = "POST"
        db_request.registry.settings = {"remember_device.days": 30}

        form_obj = form_class.return_value
        form_obj.validate.return_value = False
        form_obj.totp_value.data = "test-otp-secret"

        result = views.two_factor_and_totp_validate(db_request, _form_class=form_class)

        two_factor_token_service.loads.assert_called_once_with(
            db_request.query_string, return_timestamp=True
        )
        assert result == {"totp_form": form_obj, "remember_device_days": 30}
        assert form_obj.totp_value.data == ""

    def test_two_factor_token_missing_userid(
        self, pyramid_request, two_factor_token_service, mocker
    ):
        pyramid_request.query_string = two_factor_token_service.dumps({})
        mocker.spy(two_factor_token_service, "loads")

        mocker.spy(pyramid_request.session, "flash")
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="redirect_to"
        )

        result = views.two_factor_and_totp_validate(pyramid_request)

        two_factor_token_service.loads.assert_called_once_with(
            pyramid_request.query_string, return_timestamp=True
        )
        pyramid_request.route_path.assert_called_once_with("accounts.login")
        pyramid_request.session.flash.assert_called_once_with(
            "Invalid or expired two factor login.", queue="error"
        )

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "redirect_to"

    def test_two_factor_token_invalid(
        self, pyramid_request, two_factor_token_service, mocker
    ):
        pyramid_request.query_string = "not-a-valid-token"

        mocker.spy(pyramid_request.session, "flash")
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="redirect_to"
        )

        result = views.two_factor_and_totp_validate(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "redirect_to"
        pyramid_request.session.flash.assert_called_once_with(
            "Invalid or expired two factor login.", queue="error"
        )

    def test_two_factor_and_totp_validate_device_not_known(
        self,
        db_request,
        two_factor_token_service,
        user_service,
        two_factor_user,
        mocker,
    ):
        mocker.patch.object(
            user_service, "device_is_known", autospec=True, return_value=False
        )
        mocker.patch.object(
            user_service, "check_totp_value", autospec=True, return_value=True
        )
        mocker.patch.object(
            db_request,
            "route_path",
            autospec=True,
            return_value="/account/confirm-login/",
        )
        db_request.query_string = two_factor_token_service.dumps(
            {"userid": two_factor_user.id}
        )

        db_request.registry.settings = {"remember_device.days": 30}
        db_request.method = "POST"
        db_request.POST = MultiDict({"totp_value": "123456"})
        result = two_factor_and_totp_validate(db_request)

        assert isinstance(result, HTTPSeeOther)
        db_request.route_path.assert_called_once_with("accounts.confirm-login")
        user_service.device_is_known.assert_called_once_with(
            str(two_factor_user.id), db_request, "totp"
        )


class TestWebAuthn:
    def test_webauthn_get_options_already_authenticated(self, pyramid_request):
        pyramid_request.user = UserFactory.build()

        result = views.webauthn_authentication_options(pyramid_request)

        assert result == {"fail": {"errors": ["Already authenticated"]}}

    def test_webauthn_get_options_invalid_token(
        self, pyramid_request, two_factor_token_service, mocker
    ):
        pyramid_request.query_string = "not-a-valid-token"
        mocker.spy(pyramid_request.session, "flash")

        result = views.webauthn_authentication_options(pyramid_request)

        pyramid_request.session.flash.assert_called_once_with(
            "Invalid or expired two factor login.", queue="error"
        )
        assert result == {"fail": {"errors": ["Invalid or expired two factor login."]}}

    def test_webauthn_get_options(
        self,
        db_request,
        two_factor_token_service,
        user_service,
        two_factor_user,
        mocker,
    ):
        db_request.query_string = two_factor_token_service.dumps(
            {"userid": two_factor_user.id, "redirect_to": "foobar"}
        )
        db_request.session = Session()
        mocker.spy(views, "_get_two_factor_data")
        mocker.spy(user_service, "get_webauthn_assertion_options")

        result = views.webauthn_authentication_options(db_request)

        views._get_two_factor_data.assert_called_once_with(db_request)
        user_service.get_webauthn_assertion_options.assert_called_once_with(
            str(two_factor_user.id),
            challenge=db_request.session.get_webauthn_challenge(),
            rp_id=db_request.domain,
        )
        assert result == user_service.get_webauthn_assertion_options.spy_return

    def test_webauthn_validate_already_authenticated(
        self, pyramid_request, pyramid_config
    ):
        pyramid_config.testing_securitypolicy(identity=UserFactory.build())

        result = views.webauthn_authentication_validate(pyramid_request)

        assert result == {"fail": {"errors": ["Already authenticated"]}}

    def test_webauthn_validate_invalid_token(
        self, pyramid_request, two_factor_token_service, mocker
    ):
        pyramid_request.query_string = "not-a-valid-token"
        mocker.spy(pyramid_request.session, "flash")

        result = views.webauthn_authentication_validate(pyramid_request)

        pyramid_request.session.flash.assert_called_once_with(
            "Invalid or expired two factor login.", queue="error"
        )
        assert result == {"fail": {"errors": ["Invalid or expired two factor login."]}}

    def test_webauthn_validate_invalid_form(
        self, db_request, two_factor_token_service, two_factor_user, mocker
    ):
        db_request.query_string = two_factor_token_service.dumps(
            {"userid": two_factor_user.id, "redirect_to": "foobar"}
        )
        db_request.POST = MultiDict()
        db_request.session = Session()
        mocker.spy(views, "_get_two_factor_data")
        mocker.spy(db_request.session, "get_webauthn_challenge")
        mocker.spy(db_request.session, "clear_webauthn_challenge")

        result = views.webauthn_authentication_validate(db_request)

        views._get_two_factor_data.assert_called_once_with(db_request)
        db_request.session.get_webauthn_challenge.assert_called_once_with()
        db_request.session.clear_webauthn_challenge.assert_called_once_with()

        assert result == {"fail": {"errors": ["This field is required."]}}

    @pytest.mark.parametrize("has_recovery_codes", [True, False])
    @pytest.mark.parametrize("remember_device", [True, False])
    def test_webauthn_validate(
        self,
        db_request,
        two_factor_token_service,
        user_service,
        two_factor_user,
        has_recovery_codes,
        remember_device,
        mocker,
    ):
        _login_user = mocker.patch.object(views, "_login_user", autospec=True)
        _remember_device = mocker.patch.object(views, "_remember_device", autospec=True)
        send_email = mocker.patch.object(
            views, "send_recovery_code_reminder_email", autospec=True
        )

        user = two_factor_user
        if has_recovery_codes:
            RecoveryCodeFactory.create(user=user)
        webauthn = WebAuthnFactory.create(
            user=user,
            label="webauthn_label",
            credential_id=bytes_to_base64url(b"credential"),
            sign_count=0,
        )

        db_request.query_string = two_factor_token_service.dumps(
            {"userid": user.id, "redirect_to": "/foobar"}
        )
        db_request.session = Session()
        mocker.spy(views, "_get_two_factor_data")
        mocker.spy(db_request.session, "get_webauthn_challenge")
        mocker.spy(db_request.session, "clear_webauthn_challenge")
        db_request.user = user

        form_class = mocker.patch.object(
            views, "WebAuthnAuthenticationForm", autospec=True
        )
        form_obj = form_class.return_value
        form_obj.validate.return_value = True
        form_obj.validated_credential = VerifiedAuthentication(
            credential_id=b"credential",
            new_sign_count=1,
            credential_device_type="single_device",
            credential_backed_up=False,
            user_verified=False,
        )
        form_obj.remember_device.data = remember_device

        result = views.webauthn_authentication_validate(db_request)

        views._get_two_factor_data.assert_called_once_with(db_request)
        form_class.assert_called_once_with(
            db_request.POST,
            request=db_request,
            user_id=str(user.id),
            user_service=user_service,
            challenge=db_request.session.get_webauthn_challenge.spy_return,
            origin=db_request.host_url,
            rp_id=db_request.domain,
        )
        _login_user.assert_called_once_with(
            db_request, str(user.id), "webauthn", two_factor_label="webauthn_label"
        )
        assert webauthn.sign_count == 1
        db_request.session.get_webauthn_challenge.assert_called_once_with()
        db_request.session.clear_webauthn_challenge.assert_called_once_with()
        if has_recovery_codes:
            send_email.assert_not_called()
        else:
            send_email.assert_called_once_with(db_request, user)

        if remember_device:
            _remember_device.assert_called_once_with(
                db_request, db_request.response, str(user.id), "webauthn"
            )
        else:
            _remember_device.assert_not_called()

        assert result == {
            "success": "Successful WebAuthn assertion",
            "redirect_to": "/foobar",
        }


class TestRememberDevice:
    def test_check_remember_device_token_valid(
        self, pyramid_request, remember_device_token_service
    ):
        pyramid_request.cookies[REMEMBER_DEVICE_COOKIE] = (
            remember_device_token_service.dumps({"user_id": 1})
        )
        assert views._check_remember_device_token(pyramid_request, 1)

    def test_check_remember_device_token_invalid_no_cookie(self, pyramid_request):
        assert not views._check_remember_device_token(pyramid_request, 1)

    def test_check_remember_device_token_invalid_bad_token(
        self, pyramid_request, remember_device_token_service
    ):
        pyramid_request.cookies[REMEMBER_DEVICE_COOKIE] = "token"
        assert not views._check_remember_device_token(pyramid_request, 1)

    def test_check_remember_device_token_invalid_wrong_user(
        self, pyramid_request, remember_device_token_service
    ):
        pyramid_request.cookies[REMEMBER_DEVICE_COOKIE] = (
            remember_device_token_service.dumps({"user_id": 999})
        )
        assert not views._check_remember_device_token(pyramid_request, 1)

    def test_remember_device(
        self, pyramid_request, remember_device_token_service, mocker
    ):
        mocker.spy(remember_device_token_service, "dumps")
        pyramid_request.scheme = "https"
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="/accounts/login"
        )
        pyramid_request.user = UserFactory.build()
        mocker.patch.object(pyramid_request.user, "record_event", autospec=True)
        pyramid_request.registry.settings = {
            "remember_device.seconds": datetime.timedelta(days=30).total_seconds()
        }
        response = pyramid_request.response
        mocker.spy(response, "set_cookie")

        views._remember_device(pyramid_request, response, 1, "webauthn")

        remember_device_token_service.dumps.assert_called_once_with({"user_id": "1"})
        response.set_cookie.assert_called_once_with(
            REMEMBER_DEVICE_COOKIE,
            remember_device_token_service.dumps.spy_return,
            max_age=datetime.timedelta(days=30).total_seconds(),
            httponly=True,
            secure=True,
            samesite=b"strict",
            path="/accounts/login",
        )
        pyramid_request.route_path.assert_called_once_with("accounts.login")
        pyramid_request.user.record_event.assert_called_once_with(
            tag=EventTag.Account.TwoFactorDeviceRemembered,
            request=pyramid_request,
            additional={"two_factor_method": "webauthn"},
        )


class TestRecoveryCode:
    @pytest.fixture
    def form_class(self, mocker):
        return mocker.create_autospec(RecoveryCodeAuthenticationForm)

    def test_already_authenticated(self, pyramid_request, mocker):
        pyramid_request.user = UserFactory.build()
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="redirect_to"
        )

        result = views.recovery_code(pyramid_request)

        pyramid_request.route_path.assert_called_once_with("manage.projects")

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "redirect_to"

    def test_two_factor_token_invalid(
        self, pyramid_request, two_factor_token_service, mocker
    ):
        pyramid_request.query_string = "not-a-valid-token"
        mocker.spy(pyramid_request.session, "flash")
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="redirect_to"
        )

        result = views.recovery_code(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        pyramid_request.route_path.assert_called_once_with("accounts.login")
        assert result.headers["Location"] == "redirect_to"
        pyramid_request.session.flash.assert_called_once_with(
            "Invalid or expired two factor login.", queue="error"
        )

    def test_get_returns_form(
        self,
        db_request,
        two_factor_token_service,
        user_service,
        two_factor_user,
        form_class,
        mocker,
    ):
        db_request.query_string = two_factor_token_service.dumps(
            {"userid": two_factor_user.id}
        )
        mocker.spy(two_factor_token_service, "loads")

        result = views.recovery_code(db_request, _form_class=form_class)

        two_factor_token_service.loads.assert_called_once_with(
            db_request.query_string, return_timestamp=True
        )
        assert result == {"form": form_class.return_value}
        form_class.assert_called_once_with(
            db_request.POST,
            request=db_request,
            user_id=str(two_factor_user.id),
            user_service=user_service,
        )

    @pytest.mark.parametrize("redirect_url", ["/test_redirect_url", None])
    def test_recovery_code_auth_with_confirmed_unique_login(
        self, db_request, two_factor_token_service, form_class, redirect_url, mocker
    ):
        remember = mocker.patch.object(
            views, "remember", autospec=True, return_value=[("foo", "bar")]
        )

        user = UserFactory.create(
            with_terms_of_service_agreement=True,
            last_login=(
                datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
            ),
        )
        # A confirmed login from this IP makes the device known.
        UserUniqueLoginFactory.create(
            user=user,
            ip_address=db_request.ip_address,
            status=UniqueLoginStatus.CONFIRMED,
        )
        mocker.patch.object(user, "record_event", autospec=True, return_value=None)

        query_params = {"userid": user.id}
        if redirect_url:
            query_params["redirect_to"] = redirect_url
        db_request.query_string = two_factor_token_service.dumps(query_params)

        db_request.method = "POST"
        db_request.session = Session({"a": "b", "foo": "bar"})
        for method in (
            "invalidate",
            "new_csrf_token",
            "record_auth_timestamp",
            "flash",
        ):
            mocker.spy(db_request.session, method)
        db_request.registry.settings = {"terms.revision": "initial"}

        form_class.return_value.validate.return_value = True
        form_class.return_value.recovery_code_value.data = "recovery-code"

        result = views.recovery_code(db_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == (redirect_url or "/")
        assert result.headers["Set-Cookie"].startswith("user_id__insecure=")

        remember.assert_called_once_with(db_request, str(user.id))
        db_request.session.invalidate.assert_called_once_with()
        db_request.session.new_csrf_token.assert_called_once_with()
        assert user.record_event.call_args_list == [
            mocker.call(
                tag=EventTag.Account.LoginSuccess,
                request=db_request,
                additional={
                    "two_factor_method": "recovery-code",
                    "two_factor_label": None,
                },
            ),
            mocker.call(
                tag=EventTag.Account.RecoveryCodesUsed,
                request=db_request,
            ),
        ]
        db_request.session.flash.assert_called_once_with(
            "Recovery code accepted. The supplied code cannot be used again.",
            queue="success",
        )
        db_request.session.record_auth_timestamp.assert_called_once_with()

    def test_recovery_code_form_invalid(
        self, db_request, two_factor_token_service, two_factor_user, form_class, mocker
    ):
        db_request.query_string = two_factor_token_service.dumps(
            {"userid": two_factor_user.id}
        )
        mocker.spy(two_factor_token_service, "loads")
        db_request.method = "POST"

        form_obj = form_class.return_value
        form_obj.validate.return_value = False
        form_obj.recovery_code_value.data = "invalid-recovery-code"

        result = views.recovery_code(db_request, _form_class=form_class)

        two_factor_token_service.loads.assert_called_once_with(
            db_request.query_string, return_timestamp=True
        )
        assert result == {"form": form_obj}
        assert form_obj.recovery_code_value.data == ""

    def test_recovery_code_auth_invalid_token(
        self, pyramid_request, two_factor_token_service, mocker
    ):
        mocker.patch.object(
            two_factor_token_service, "loads", autospec=True, side_effect=TokenException
        )
        mocker.spy(pyramid_request.session, "flash")
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="redirect_to"
        )

        result = views.recovery_code(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        pyramid_request.route_path.assert_called_once_with("accounts.login")
        assert result.headers["Location"] == "redirect_to"
        pyramid_request.session.flash.assert_called_once_with(
            "Invalid or expired two factor login.", queue="error"
        )

    def test_recovery_code_device_not_known(
        self,
        db_request,
        two_factor_token_service,
        user_service,
        two_factor_user,
        form_class,
        mocker,
    ):
        mocker.patch.object(
            user_service, "device_is_known", autospec=True, return_value=False
        )
        mocker.patch.object(
            db_request,
            "route_path",
            autospec=True,
            return_value="/account/confirm-login/",
        )
        db_request.query_string = two_factor_token_service.dumps(
            {"userid": two_factor_user.id}
        )
        db_request.method = "POST"
        form_class.return_value.validate.return_value = True
        form_class.return_value.recovery_code_value.data = "test-recovery-code"

        result = views.recovery_code(db_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/account/confirm-login/"
        db_request.route_path.assert_called_once_with("accounts.confirm-login")
        user_service.device_is_known.assert_called_once_with(
            str(two_factor_user.id), db_request, two_factor_method="recovery-code"
        )


class TestLogout:
    @pytest.mark.parametrize("next_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_empty(self, pyramid_request, next_url):
        if next_url is not None:
            pyramid_request.GET["next"] = next_url

        pyramid_request.user = UserFactory.build()

        assert views.logout(pyramid_request) == {
            "redirect": {"field": "next", "data": next_url or "/"}
        }

    def test_post_forgets_user(self, pyramid_request, mocker):
        forget = mocker.patch.object(
            views, "forget", autospec=True, return_value=[("foo", "bar")]
        )

        pyramid_request.user = UserFactory.build()
        pyramid_request.method = "POST"
        mocker.spy(pyramid_request.session, "invalidate")

        security_policy = mocker.create_autospec(MultiSecurityPolicy, instance=True)
        pyramid_request.registry.registerUtility(security_policy, ISecurityPolicy)

        result = views.logout(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert result.headers["foo"] == "bar"
        forget.assert_called_once_with(pyramid_request)
        pyramid_request.session.invalidate.assert_called_once_with()
        security_policy.reset.assert_called_once_with(pyramid_request)

    @pytest.mark.parametrize(
        # The set of all possible next URLs. Since this set is infinite, we
        # test only a finite set of reasonable URLs.
        ("expected_next_url", "observed_next_url"),
        [
            ("/security/", "/security/"),
            ("http://example.com", "/"),
            ("\n/example.com/", "/"),
        ],
    )
    def test_post_redirects_user(
        self, pyramid_request, expected_next_url, observed_next_url
    ):
        pyramid_request.user = UserFactory.build()
        pyramid_request.method = "POST"
        pyramid_request.POST["next"] = expected_next_url

        result = views.logout(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == observed_next_url

    @pytest.mark.parametrize(
        # The set of all possible next URLs. Since this set is infinite, we
        # test only a finite set of reasonable URLs.
        ("expected_next_url", "observed_next_url"),
        [
            ("/security/", "/security/"),
            ("http://example.com", "/"),
            ("\n/example.com/", "/"),
        ],
    )
    def test_get_redirects_anonymous_user(
        self, pyramid_request, expected_next_url, observed_next_url
    ):
        pyramid_request.user = None
        pyramid_request.method = "GETT"
        pyramid_request.GET["next"] = expected_next_url

        result = views.logout(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == observed_next_url


class TestRegister:
    def test_get(self, db_request, pyramid_services, mocker):
        self._register_form_services(pyramid_services)
        form_class = mocker.create_autospec(RegistrationForm)

        result = views.register(db_request, _form_class=form_class)

        assert result["form"] is form_class.return_value

    def test_redirect_authenticated_user(self, pyramid_request, mocker):
        pyramid_request.user = UserFactory.build()
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="/the-redirect"
        )
        result = views.register(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_register_honeypot(self, db_request, user_service, metrics, mocker):
        db_request.method = "POST"
        mocker.spy(user_service, "create_user")
        mocker.spy(user_service, "add_email")
        mocker.patch.object(db_request, "route_path", autospec=True, return_value="/")
        db_request.POST = {"confirm_form": "fuzzywuzzy@bears.com"}
        send_email = mocker.patch.object(
            views, "send_email_verification_email", autospec=True
        )

        result = views.register(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        user_service.create_user.assert_not_called()
        user_service.add_email.assert_not_called()
        send_email.assert_not_called()
        metrics.increment.assert_called_once_with(
            "warehouse.accounts.register", tags=["outcome:honeypot"]
        )

    def test_register_counts_an_authenticated_post(self, db_request, metrics):
        """Every POST lands in exactly one outcome, so the tags sum to attempts."""
        db_request.method = "POST"
        db_request.user = UserFactory.create()
        db_request.route_path = lambda name: "/the-redirect"

        assert isinstance(views.register(db_request), HTTPSeeOther)
        metrics.increment.assert_any_call(
            "warehouse.accounts.register", tags=["outcome:authenticated"]
        )

    def _register_form_services(self, pyramid_services, *, captcha_enabled=False):
        """Register the services `register()` needs to build its form."""
        pyramid_services.register_service(
            NullPasswordBreachedService(), IPasswordBreachedService, None, name=""
        )
        pyramid_services.register_service(
            SimpleNamespace(
                enabled=captcha_enabled,
                csp_policy={},
                verify_response=lambda response: None,
            ),
            ICaptchaService,
            None,
            name="captcha",
        )
        pyramid_services.register_service(
            SimpleNamespace(merge=lambda policy: None), None, None, name="csp"
        )

    def _post_a_registration(self, db_request):
        """Fill in a POST body that would otherwise pass form validation."""
        db_request.method = "POST"
        db_request.POST.update(
            {
                "username": "username_value",
                "new_password": "MyStr0ng!shP455w0rd",
                "password_confirm": "MyStr0ng!shP455w0rd",
                "email": "foo@bar.com",
                "full_name": "full_name",
                "acceptable_use": "y",
            }
        )

    @pytest.mark.parametrize(
        ("resets_in", "retry_after", "message"),
        [
            (
                datetime.timedelta(seconds=3300),
                "3300",
                (
                    "Too many registration attempts from your network. Please try "
                    "again in 55 minutes."
                ),
            ),
            (
                None,
                None,
                (
                    "Too many registration attempts from your network. Please try "
                    "again later."
                ),
            ),
        ],
    )
    def test_register_ratelimited(
        self,
        db_request,
        pyramid_services,
        metrics,
        ratelimit_service,
        mocker,
        resets_in,
        retry_after,
        message,
    ):
        """A denied attempt returns 429 with a form error and the typed values
        intact.
        """
        self._register_form_services(pyramid_services)
        mocker.patch.object(ratelimit_service, "hit", return_value=False)
        mocker.patch.object(ratelimit_service, "resets_in", return_value=resets_in)
        self._post_a_registration(db_request)

        result = views.register(db_request)

        assert db_request.response.status_int == 429
        # The typed values survive, so the user is not asked to start over.
        assert result["form"].email.data == "foo@bar.com"
        assert result["form"].username.data == "username_value"
        # Only the form-level key: the limiter runs before validate(), so no
        # per-field errors appear.
        assert result["form"].errors == {"": [message]}
        # Asserted on the raw header: WebOb's `retry_after` getter parses it
        # back into an absolute datetime.
        assert db_request.response.headers.get("Retry-After") == retry_after
        ratelimit_service.hit.assert_called_once_with(db_request.remote_addr)
        metrics.increment.assert_any_call(
            "warehouse.accounts.register", tags=["outcome:ratelimited"]
        )
        metrics.increment.assert_any_call(
            "warehouse.accounts.register.ratelimited", tags=["ratelimiter:ip"]
        )

    @pytest.mark.usefixtures("no_email_deliverability_check")
    @pytest.mark.parametrize("remote_addr", [None, ""])
    def test_register_skips_the_limiter_without_a_remote_addr(
        self, db_request, pyramid_services, metrics, ratelimit_service, remote_addr
    ):
        """An unkeyable request is not metered into one bucket shared by all.

        Gunicorn on a unix socket sends '' as REMOTE_ADDR, not None, so both
        are exercised here.
        """
        self._register_form_services(pyramid_services)
        db_request.method = "POST"
        db_request.POST.update({"username": "username_value", "email": "not-an-email"})
        db_request.remote_addr = remote_addr

        views.register(db_request)

        assert ratelimit_service.hit.call_count == 0
        # Counted, so a limiter that has stopped running is not silent.
        metrics.increment.assert_any_call("warehouse.accounts.register.unmetered")

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_register_counts_invalid_attempts(
        self, db_request, pyramid_services, metrics, ratelimit_service
    ):
        """A failed attempt is charged, since validation costs DNS either way."""
        self._register_form_services(pyramid_services)

        db_request.method = "POST"
        db_request.POST.update({"username": "username_value", "email": "not-an-email"})

        result = views.register(db_request)

        assert result["form"].errors
        ratelimit_service.hit.assert_called_once_with(db_request.remote_addr)
        metrics.increment.assert_any_call(
            "warehouse.accounts.register", tags=["outcome:invalid"]
        )

    def test_register_does_not_count_page_loads(
        self, db_request, pyramid_services, metrics, ratelimit_service
    ):
        """A GET is a page view, so it is neither counted nor charged."""
        self._register_form_services(pyramid_services)

        views.register(db_request)

        assert ratelimit_service.hit.call_count == 0
        assert not [
            call
            for call in metrics.increment.call_args_list
            if call.args == ("warehouse.accounts.register",)
        ]

    @pytest.mark.usefixtures("no_email_deliverability_check")
    def test_register_redirect(
        self,
        db_request,
        pyramid_services,
        user_service,
        metrics,
        ratelimit_service,
        mocker,
    ):
        self._register_form_services(pyramid_services, captcha_enabled=True)
        register_limiter = DummyRateLimiter()
        mocker.spy(register_limiter, "hit")
        pyramid_services.register_service(
            register_limiter, IRateLimiter, None, name="accounts.register"
        )
        mocker.spy(user_service, "create_user")
        mocker.spy(user_service, "add_email")
        record_event = mocker.patch(
            "warehouse.accounts.models.HasEvents.record_event", autospec=True
        )
        send_email = mocker.patch.object(
            views, "send_email_verification_email", autospec=True
        )
        mocker.patch.object(db_request, "route_path", autospec=True, return_value="/")
        db_request.session = Session()
        db_request.registry.settings = {"terms.revision": "initial"}
        self._post_a_registration(db_request)
        db_request.POST.update({"g-recaptcha-response": "captchavalue"})

        result = views.register(db_request)

        user = user_service.create_user.spy_return
        email = user_service.add_email.spy_return
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert result.headers["Set-Cookie"].startswith("user_id__insecure=")
        user_service.create_user.assert_called_once_with(
            "username_value", "full_name", "MyStr0ng!shP455w0rd"
        )
        user_service.add_email.assert_called_once_with(
            user.id, "foo@bar.com", primary=True
        )
        send_email.assert_called_once_with(db_request, (user, email))
        assert record_event.call_args_list == [
            mocker.call(
                user,
                tag=EventTag.Account.AccountCreate,
                request=db_request,
                additional={"email": "foo@bar.com"},
            ),
            mocker.call(
                user,
                tag=EventTag.Account.LoginSuccess,
                request=db_request,
                additional={
                    "two_factor_method": "registration",
                    "two_factor_label": None,
                },
            ),
        ]
        metrics.increment.assert_any_call(
            "warehouse.accounts.register", tags=["outcome:ok"]
        )
        # Successes stay charged against the register limiter, keyed by IP;
        # the verification email is charged against email.verify, by user.
        register_limiter.hit.assert_called_once_with(db_request.remote_addr)
        ratelimit_service.hit.assert_called_once_with(user.id)

    def test_register_fails_with_admin_flag_set(self, db_request, metrics, mocker):
        # This flag was already set via migration, just need to enable it
        flag = db_request.db.get(
            AdminFlag, AdminFlagValue.DISALLOW_NEW_USER_REGISTRATION.value
        )
        flag.enabled = True

        self._post_a_registration(db_request)

        mocker.spy(db_request.session, "flash")
        mocker.patch.object(db_request, "route_path", autospec=True, return_value="/")

        result = views.register(db_request)

        assert isinstance(result, HTTPSeeOther)
        db_request.session.flash.assert_called_once_with(
            "New user registration temporarily disabled. "
            "See https://pypi.org/help#admin-intervention for details.",
            queue="error",
        )
        metrics.increment.assert_any_call(
            "warehouse.accounts.register", tags=["outcome:disabled"]
        )


class TestRequestPasswordReset:
    @pytest.fixture
    def form_class(self, mocker):
        form_class = mocker.create_autospec(RequestPasswordResetForm)
        form_class.return_value.validate.return_value = True
        return form_class

    @pytest.fixture
    def reset_limiter(self, user_service):
        """The ``DummyRateLimiter`` the real user service hands out by default."""
        return user_service.ratelimiters["password.reset"]

    def test_get(self, pyramid_request, user_service, mocker):
        form_class = mocker.create_autospec(RequestPasswordResetForm)
        mocker.spy(pyramid_request, "find_service")

        result = views.request_password_reset(pyramid_request, _form_class=form_class)

        assert result["form"] is form_class.return_value
        form_class.assert_called_once_with(
            pyramid_request.POST, user_service=user_service
        )
        pyramid_request.find_service.assert_called_once_with(IUserService, context=None)

    def test_request_password_reset(
        self, pyramid_request, user_service, token_service, form_class, mocker
    ):
        user = UserFactory.create(with_verified_primary_email=True)
        mock_record_event = mocker.patch(
            "warehouse.accounts.models.HasEvents.record_event",
            autospec=True,
            return_value=True,
        )
        pyramid_request.method = "POST"
        mocker.spy(user_service, "get_user_by_username")
        mocker.spy(pyramid_request, "find_service")
        form_class.return_value.username_or_email.data = user.username
        send_password_reset_email = mocker.patch.object(
            views, "send_password_reset_email", autospec=True
        )

        result = views.request_password_reset(pyramid_request, _form_class=form_class)

        assert result == {"n_hours": token_service.max_age // 60 // 60}
        user_service.get_user_by_username.assert_called_once_with(user.username)
        assert pyramid_request.find_service.call_args_list == [
            mocker.call(IUserService, context=None),
            mocker.call(ITokenService, name="password"),
        ]
        form_class.return_value.validate.assert_called_once_with()
        form_class.assert_called_once_with(
            pyramid_request.POST, user_service=user_service
        )
        send_password_reset_email.assert_called_once_with(
            pyramid_request, (user, user.primary_email)
        )
        mock_record_event.assert_called_once_with(
            user,
            tag=EventTag.Account.PasswordResetRequest,
            request=pyramid_request,
        )

    @pytest.mark.parametrize(
        ("emails", "requested"),
        [
            (["foo@example.com"], "foo@example.com"),
            (["foo@example.com", "other@example.com"], "other@example.com"),
        ],
    )
    def test_request_password_reset_with_email(
        self,
        pyramid_request,
        user_service,
        token_service,
        form_class,
        reset_limiter,
        emails,
        requested,
        mocker,
    ):
        user = UserFactory.create()
        for address in emails:
            EmailFactory.create(user=user, email=address, verified=True)
        requested_email = next(e for e in user.emails if e.email == requested)
        mock_record_event = mocker.patch(
            "warehouse.accounts.models.HasEvents.record_event", autospec=True
        )
        pyramid_request.method = "POST"
        mocker.spy(user_service, "get_user_by_username")
        mocker.spy(user_service, "get_user_by_email")
        mocker.spy(reset_limiter, "test")
        mocker.spy(reset_limiter, "hit")
        mocker.spy(pyramid_request, "find_service")
        form_class.return_value.username_or_email.data = requested
        send_password_reset_email = mocker.patch.object(
            views, "send_password_reset_email", autospec=True
        )

        result = views.request_password_reset(pyramid_request, _form_class=form_class)

        assert result == {"n_hours": token_service.max_age // 60 // 60}
        user_service.get_user_by_username.assert_called_once_with(requested)
        user_service.get_user_by_email.assert_called_once_with(requested)
        assert pyramid_request.find_service.call_args_list == [
            mocker.call(IUserService, context=None),
            mocker.call(ITokenService, name="password"),
        ]
        form_class.return_value.validate.assert_called_once_with()
        form_class.assert_called_once_with(
            pyramid_request.POST, user_service=user_service
        )
        send_password_reset_email.assert_called_once_with(
            pyramid_request, (user, requested_email)
        )
        mock_record_event.assert_called_once_with(
            user,
            tag=EventTag.Account.PasswordResetRequest,
            request=pyramid_request,
        )
        reset_limiter.test.assert_called_once_with(user.id)
        reset_limiter.hit.assert_called_once_with(user.id)

    def test_too_many_password_reset_requests(
        self, pyramid_request, user_service, form_class, reset_limiter, mocker
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="foo@example.com", verified=True)
        pyramid_request.method = "POST"
        mocker.spy(user_service, "get_user_by_username")
        mocker.spy(user_service, "get_user_by_email")
        mocker.patch.object(reset_limiter, "test", autospec=True, return_value=False)
        mocker.patch.object(reset_limiter, "resets_in", autospec=True, return_value=600)
        mocker.spy(pyramid_request, "find_service")
        form_class.return_value.username_or_email.data = "foo@example.com"

        with pytest.raises(TooManyPasswordResetRequests):
            views.request_password_reset(pyramid_request, _form_class=form_class)

        user_service.get_user_by_username.assert_called_once_with("foo@example.com")
        user_service.get_user_by_email.assert_called_once_with("foo@example.com")
        pyramid_request.find_service.assert_called_once_with(IUserService, context=None)
        form_class.return_value.validate.assert_called_once_with()
        form_class.assert_called_once_with(
            pyramid_request.POST, user_service=user_service
        )
        reset_limiter.test.assert_called_once_with(user.id)
        reset_limiter.resets_in.assert_called_once_with(user.id)

    def test_password_reset_prohibited(
        self, pyramid_request, token_service, form_class, mocker
    ):
        user = UserFactory.create(
            with_verified_primary_email=True,
            prohibit_password_reset=True,
        )
        mock_record_event = mocker.patch(
            "warehouse.accounts.models.HasEvents.record_event",
            autospec=True,
            return_value=True,
        )
        send_password_reset_email = mocker.patch.object(
            views, "send_password_reset_email", autospec=True
        )
        pyramid_request.method = "POST"
        form_class.return_value.username_or_email.data = user.username

        result = views.request_password_reset(pyramid_request, _form_class=form_class)

        # Response must be indistinguishable from a normal user reset
        assert result == {"n_hours": token_service.max_age // 60 // 60}
        assert not isinstance(result, HTTPSeeOther)

        send_password_reset_email.assert_not_called()
        mock_record_event.assert_called_once_with(
            user,
            tag=EventTag.Account.PasswordResetAttempt,
            request=pyramid_request,
        )

    def test_password_reset_with_nonexistent_email(
        self, pyramid_request, user_service, form_class, mocker
    ):
        pyramid_request.method = "POST"
        mocker.spy(user_service, "get_user_by_username")
        mocker.spy(user_service, "get_user_by_email")
        form_class.return_value.username_or_email.data = "foo@bar.net"

        result = views.request_password_reset(pyramid_request, _form_class=form_class)

        assert result == {"n_hours": 6}
        user_service.get_user_by_username.assert_called_once_with("foo@bar.net")
        user_service.get_user_by_email.assert_called_once_with("foo@bar.net")

    def test_redirect_authenticated_user(self, pyramid_request, mocker):
        pyramid_request.user = UserFactory.build()
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="/the-redirect"
        )
        result = views.request_password_reset(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    @pytest.mark.parametrize(
        "user_input",
        [
            "email",
            "username",
        ],
    )
    def test_unverified_email_sends_alt_notice(self, db_request, mocker, user_input):
        unverified_email = EmailFactory(verified=False)

        form_input = {
            "email": unverified_email.email,
            "username": unverified_email.user.username,
        }.get(user_input)

        mock_send_email = mocker.patch(
            "warehouse.accounts.views.send_password_reset_unverified_email",
            autospec=True,
            return_value=None,
        )
        # Prevent form's validation from checking deliverability
        mock_form_validation = mocker.patch(
            "warehouse.accounts.forms."
            "RequestPasswordResetForm.validate_username_or_email",
            autospec=True,
            return_value=True,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"username_or_email": form_input})

        result = views.request_password_reset(db_request)

        assert result == {"n_hours": 6}
        mock_form_validation.assert_called_once()
        mock_send_email.assert_called_once_with(
            db_request, (unverified_email.user, unverified_email)
        )
        db_request.log.warning.assert_called_once_with(
            "User requested password reset for unverified email",
            username=unverified_email.user.username,
            email_address=unverified_email.email,
        )


class TestResetPassword:
    @pytest.fixture
    def form_class(self, mocker):
        return mocker.create_autospec(ResetPasswordForm)

    @pytest.fixture
    def reset_limiter(self, pyramid_services, ratelimit_service):
        pyramid_services.register_service(
            ratelimit_service, IRateLimiter, None, name="password.reset"
        )
        return ratelimit_service

    @pytest.fixture
    def error_request(self, pyramid_request, breach_service, mocker):
        """A request whose token check fails before the form is built."""
        pyramid_request.GET["token"] = "RANDOM_KEY"
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="/"
        )
        mocker.spy(pyramid_request.session, "flash")
        return pyramid_request

    @pytest.mark.parametrize("dates_utc", [True, False])
    def test_get(
        self,
        db_request,
        user_service,
        token_service,
        breach_service,
        form_class,
        password_reset_token,
        dates_utc,
        mocker,
    ):
        user = UserFactory.create()
        last_login = (
            user.last_login if dates_utc else user.last_login.replace(tzinfo=None)
        )
        password_date = (
            user.password_date if dates_utc else user.password_date.replace(tzinfo=None)
        )
        token = password_reset_token(
            user, last_login=last_login, password_date=password_date
        )
        db_request.GET.update({"token": token})
        mocker.spy(token_service, "loads")
        mocker.spy(db_request, "find_service")

        result = views.reset_password(db_request, _form_class=form_class)

        assert result["form"] is form_class.return_value
        form_class.assert_called_once_with(
            db_request.POST,
            username=user.username,
            full_name=user.name,
            email=user.email,
            user_service=user_service,
            breach_service=breach_service,
        )
        token_service.loads.assert_called_once_with(token)
        assert db_request.find_service.call_args_list == [
            mocker.call(IUserService, context=None),
            mocker.call(IPasswordBreachedService, context=None),
            mocker.call(ITokenService, name="password"),
        ]

    @pytest.mark.parametrize("never_logged_in", [False, True])
    def test_reset_password(
        self,
        db_request,
        user_service,
        token_service,
        breach_service,
        reset_limiter,
        form_class,
        password_reset_token,
        never_logged_in,
        mocker,
    ):
        user = UserFactory.create()
        if never_logged_in:
            # The factory always fills these in, so clear them afterwards.
            user.last_login = user.password_date = None
            min_date = datetime.datetime.min.replace(tzinfo=datetime.UTC)
            token = password_reset_token(
                user, last_login=min_date, password_date=min_date
            )
        else:
            token = password_reset_token(user)
        db_request.method = "POST"
        db_request.POST.update({"token": token})
        form_obj = form_class.return_value
        form_obj.validate.return_value = True
        form_obj.new_password.data = "password_value"

        send_email = mocker.patch.object(
            views, "send_password_change_email", autospec=True
        )
        mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/account/login"
        )
        mocker.spy(token_service, "loads")
        mocker.spy(user_service, "update_user")
        mocker.spy(db_request, "find_service")
        mocker.spy(db_request.session, "flash")

        result = views.reset_password(db_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/account/login"
        form_obj.validate.assert_called_once_with()
        form_class.assert_called_once_with(
            db_request.POST,
            username=user.username,
            full_name=user.name,
            email=user.email,
            user_service=user_service,
            breach_service=breach_service,
        )
        db_request.route_path.assert_called_once_with("accounts.login")
        token_service.loads.assert_called_once_with(token)
        user_service.update_user.assert_called_once_with(
            user.id, password="password_value"
        )
        send_email.assert_called_once_with(db_request, user)
        db_request.session.flash.assert_called_once_with(
            "You have reset your password", queue="success"
        )
        assert db_request.find_service.call_args_list == [
            mocker.call(IUserService, context=None),
            mocker.call(IPasswordBreachedService, context=None),
            mocker.call(ITokenService, name="password"),
            mocker.call(IRateLimiter, name="password.reset"),
        ]
        reset_limiter.clear.assert_called_once_with(user.id)

    @pytest.mark.parametrize(
        ("exception", "message"),
        [
            (TokenInvalid, "Invalid token: request a new password reset link"),
            (TokenExpired, "Expired token: request a new password reset link"),
            (TokenMissing, "Invalid token: no token supplied"),
        ],
    )
    def test_reset_password_loads_failure(
        self, error_request, token_service, exception, message, mocker
    ):
        mocker.patch.object(
            token_service, "loads", autospec=True, side_effect=exception
        )

        views.reset_password(error_request)

        token_service.loads.assert_called_once_with("RANDOM_KEY")
        error_request.route_path.assert_called_once_with(
            "accounts.request-password-reset"
        )
        error_request.session.flash.assert_called_once_with(message, queue="error")

    def test_reset_password_invalid_action(self, error_request, token_service):
        error_request.GET["token"] = token_service.dumps({"action": "invalid-action"})

        views.reset_password(error_request)

        error_request.route_path.assert_called_once_with(
            "accounts.request-password-reset"
        )
        error_request.session.flash.assert_called_once_with(
            "Invalid token: not a password reset token", queue="error"
        )

    def test_reset_password_invalid_user(
        self, error_request, token_service, user_service, mocker
    ):
        user_id = "8ad1a4ac-e016-11e6-bf01-fe55135034f3"
        error_request.GET["token"] = token_service.dumps(
            {"action": "password-reset", "user.id": user_id}
        )
        mocker.spy(user_service, "get_user")

        views.reset_password(error_request)

        error_request.route_path.assert_called_once_with(
            "accounts.request-password-reset"
        )
        error_request.session.flash.assert_called_once_with(
            "Invalid token: user not found", queue="error"
        )
        user_service.get_user.assert_called_once_with(uuid.UUID(user_id))

    def test_reset_password_last_login_changed(
        self, error_request, password_reset_token
    ):
        now = datetime.datetime.now(datetime.UTC)
        later = now + datetime.timedelta(hours=1)
        user = UserFactory.create(last_login=later, username="time-traveler")
        error_request.GET["token"] = password_reset_token(user, last_login=now)

        views.reset_password(error_request)

        error_request.route_path.assert_called_once_with(
            "accounts.request-password-reset"
        )
        error_request.session.flash.assert_called_once_with(
            "Invalid token: user has logged in since this token was requested",
            queue="error",
        )

    def test_reset_password_password_date_changed(
        self, error_request, password_reset_token
    ):
        now = datetime.datetime.now(datetime.UTC)
        later = now + datetime.timedelta(hours=1)
        user = UserFactory.create(last_login=now)
        user.password_date = later
        error_request.GET["token"] = password_reset_token(user, password_date=now)

        views.reset_password(error_request)

        error_request.route_path.assert_called_once_with(
            "accounts.request-password-reset"
        )
        error_request.session.flash.assert_called_once_with(
            "Invalid token: password has already been changed since this "
            "token was requested",
            queue="error",
        )

    def test_redirect_authenticated_user(self, pyramid_request, mocker):
        pyramid_request.user = UserFactory.build()
        mocker.patch.object(
            pyramid_request, "route_path", autospec=True, return_value="/the-redirect"
        )
        result = views.reset_password(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestVerifyEmail:
    @pytest.fixture
    def error_request(self, db_request, mocker):
        """A request whose verification fails and redirects to the account page."""
        db_request.GET["token"] = "RANDOM_KEY"
        mocker.patch.object(db_request, "route_path", autospec=True, return_value="/")
        mocker.spy(db_request.session, "flash")
        return db_request

    @pytest.mark.parametrize(
        ("is_primary", "confirm_message"),
        [
            (True, "This is your primary address."),
            (False, "You can now set this email as your primary address."),
        ],
    )
    def test_verify_email(
        self, mocker, db_request, ratelimit_service, is_primary, confirm_message
    ):
        user = UserFactory(is_active=False, totp_secret=None)
        email = EmailFactory(user=user, verified=False, primary=is_primary)
        db_request.user = user
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = mocker.Mock(return_value="/")
        mock_token_service_loads = mocker.patch(
            "warehouse.accounts.services.TokenService.loads",
            return_value={"action": "email-verify", "email.id": str(email.id)},
        )
        spy_find_service = mocker.spy(db_request, "find_service")
        spy_session_flash = mocker.spy(db_request.session, "flash")

        result = views.verify_email(db_request)

        db_request.db.flush()
        assert email.verified
        assert email.domain_last_status == ["active"]
        assert user.is_active
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        db_request.route_path.assert_called_once_with("manage.account.two-factor")
        mock_token_service_loads.assert_called_once_with("RANDOM_KEY")
        ratelimit_service.clear.assert_has_calls(
            [
                mocker.call(db_request.remote_addr),
                mocker.call(user.id),
            ]
        )
        spy_session_flash.assert_called_once_with(
            f"Email address {email.email} verified. " + confirm_message, queue="success"
        )
        spy_find_service.assert_has_calls(
            [
                mocker.call(ITokenService, name="email"),
                mocker.call(IRateLimiter, name="email.add"),
                mocker.call(IRateLimiter, name="email.verify"),
                mocker.call(IDomainStatusService),
            ]
        )

    @pytest.mark.parametrize(
        ("exception", "message"),
        [
            (TokenInvalid, "Invalid token: request a new email verification link"),
            (TokenExpired, "Expired token: request a new email verification link"),
            (TokenMissing, "Invalid token: no token supplied"),
        ],
    )
    def test_verify_email_loads_failure(
        self, error_request, token_service, exception, message, mocker
    ):
        mocker.patch.object(
            token_service, "loads", autospec=True, side_effect=exception
        )

        views.verify_email(error_request)

        token_service.loads.assert_called_once_with("RANDOM_KEY")
        error_request.route_path.assert_called_once_with("manage.account")
        error_request.session.flash.assert_called_once_with(message, queue="error")

    def test_verify_email_invalid_action(self, error_request, token_service):
        error_request.GET["token"] = token_service.dumps({"action": "invalid-action"})

        views.verify_email(error_request)

        error_request.route_path.assert_called_once_with("manage.account")
        error_request.session.flash.assert_called_once_with(
            "Invalid token: not an email verification token", queue="error"
        )

    def test_verify_email_not_found(self, error_request, token_service):
        """An email that belongs to someone else is not found for this user."""
        error_request.user = UserFactory.create()
        other_email = EmailFactory.create(verified=False)
        error_request.GET["token"] = token_service.dumps(
            {"action": "email-verify", "email.id": other_email.id}
        )

        views.verify_email(error_request)

        error_request.route_path.assert_called_once_with("manage.account")
        error_request.session.flash.assert_called_once_with(
            "Email not found", queue="error"
        )
        assert not other_email.verified

    def test_verify_email_already_verified(self, error_request, token_service):
        user = UserFactory()
        email = EmailFactory(user=user, verified=True)
        error_request.user = user
        error_request.GET["token"] = token_service.dumps(
            {"action": "email-verify", "email.id": email.id}
        )

        views.verify_email(error_request)

        error_request.route_path.assert_called_once_with("manage.account")
        error_request.session.flash.assert_called_once_with(
            "Email already verified", queue="error"
        )

    def test_verify_email_with_existing_2fa(self, mocker, db_request):
        user = UserFactory(is_active=False, totp_secret=b"secret")
        email = EmailFactory(user=user, verified=False, primary=False)
        db_request.user = user
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = mocker.Mock(return_value="/")
        mocker.patch(
            "warehouse.accounts.services.TokenService.loads",
            return_value={"action": "email-verify", "email.id": str(email.id)},
        )

        assert db_request.user.has_two_factor

        result = views.verify_email(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        db_request.route_path.assert_called_once_with("manage.account")
        assert db_request.user.is_active


class TestVerifyOrganizationRole:
    @pytest.mark.parametrize(
        "desired_role", ["Member", "Manager", "Owner", "Billing Manager"]
    )
    def test_verify_organization_role(
        self, db_request, token_service, monkeypatch, desired_role
    ):
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
            token="RANDOM_KEY",
        )
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            organization=organization,
            user=owner_user,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.user = user
        db_request.method = "POST"
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/")
        db_request.remote_addr = "192.168.1.1"
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-organization-role-verify",
                "desired_role": desired_role,
                "user_id": user.id,
                "organization_id": organization.id,
                "submitter_id": owner_user.id,
            }
        )

        organization_member_added_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_member_added_email",
            organization_member_added_email,
        )
        added_as_organization_member_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            views,
            "send_added_as_organization_member_email",
            added_as_organization_member_email,
        )

        result = views.verify_organization_role(db_request)

        db_request.db.flush()

        assert not (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == user)
            .filter(OrganizationInvitation.organization == organization)
            .one_or_none()
        )
        assert (
            db_request.db.query(OrganizationRole)
            .filter(
                OrganizationRole.organization == organization,
                OrganizationRole.user == user,
            )
            .one()
        )
        assert organization_member_added_email.calls == [
            pretend.call(
                db_request,
                {owner_user},
                user=user,
                submitter=owner_user,
                organization_name=organization.name,
                role=desired_role,
            )
        ]
        assert added_as_organization_member_email.calls == [
            pretend.call(
                db_request,
                user,
                submitter=owner_user,
                organization_name=organization.name,
                role=desired_role,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                (
                    f"You are now {desired_role} of the "
                    f"'{organization.name}' organization."
                ),
                queue="success",
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert db_request.route_path.calls == [
            pretend.call(
                "manage.organization.roles",
                organization_name=organization.normalized_name,
            )
        ]

    @pytest.mark.parametrize(
        ("exception", "message"),
        [
            (TokenInvalid, "Invalid token: request a new organization invitation"),
            (TokenExpired, "Expired token: request a new organization invitation"),
            (TokenMissing, "Invalid token: no token supplied"),
        ],
    )
    def test_verify_organization_role_loads_failure(
        self, db_request, token_service, exception, message
    ):
        def loads(token):
            raise exception

        db_request.params = {"token": "RANDOM_KEY"}
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        token_service.loads = loads

        views.verify_organization_role(db_request)

        assert db_request.route_path.calls == [pretend.call("manage.organizations")]
        assert db_request.session.flash.calls == [pretend.call(message, queue="error")]

    def test_verify_email_invalid_action(self, db_request, token_service):
        data = {"action": "invalid-action"}
        db_request.params = {"token": "RANDOM_KEY"}
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        token_service.loads = lambda a: data

        views.verify_organization_role(db_request)

        assert db_request.route_path.calls == [pretend.call("manage.organizations")]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Invalid token: not an organization invitation token", queue="error"
            )
        ]

    def test_verify_organization_role_revoked(self, db_request, token_service):
        desired_role = "Manager"
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            organization=organization,
            user=owner_user,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.user = user
        db_request.method = "POST"
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.remote_addr = "192.168.1.1"
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-organization-role-verify",
                "desired_role": desired_role,
                "user_id": user.id,
                "organization_id": organization.id,
                "submitter_id": owner_user.id,
            }
        )

        views.verify_organization_role(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Organization invitation no longer exists.",
                queue="error",
            )
        ]
        assert db_request.route_path.calls == [pretend.call("manage.organizations")]

    def test_verify_organization_role_declined(
        self, db_request, token_service, monkeypatch
    ):
        desired_role = "Manager"
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
            token="RANDOM_KEY",
        )
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            organization=organization,
            user=owner_user,
            role_name=OrganizationRoleType.Owner,
        )
        message = "Some reason to decline."

        db_request.user = user
        db_request.method = "POST"
        db_request.POST.update(
            {"token": "RANDOM_KEY", "decline": "Decline", "message": message}
        )
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.remote_addr = "192.168.1.1"
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-organization-role-verify",
                "desired_role": desired_role,
                "user_id": user.id,
                "organization_id": organization.id,
                "submitter_id": owner_user.id,
            }
        )

        organization_member_invite_declined_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            views,
            "send_organization_member_invite_declined_email",
            organization_member_invite_declined_email,
        )
        declined_as_invited_organization_member_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            views,
            "send_declined_as_invited_organization_member_email",
            declined_as_invited_organization_member_email,
        )

        result = views.verify_organization_role(db_request)

        assert not (
            db_request.db.query(OrganizationInvitation)
            .filter(OrganizationInvitation.user == user)
            .filter(OrganizationInvitation.organization == organization)
            .one_or_none()
        )
        assert organization_member_invite_declined_email.calls == [
            pretend.call(
                db_request,
                {owner_user},
                user=user,
                organization_name=organization.name,
                message=message,
            )
        ]
        assert declined_as_invited_organization_member_email.calls == [
            pretend.call(
                db_request,
                user,
                organization_name=organization.name,
            )
        ]
        assert isinstance(result, HTTPSeeOther)
        assert db_request.route_path.calls == [pretend.call("manage.organizations")]

    def test_verify_fails_with_different_user(self, db_request, token_service):
        desired_role = "Manager"
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        user_2 = UserFactory.create()
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            organization=organization,
            user=owner_user,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.user = user_2
        db_request.method = "POST"
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.remote_addr = "192.168.1.1"
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-organization-role-verify",
                "desired_role": desired_role,
                "user_id": user.id,
                "organization_id": organization.id,
                "submitter_id": owner_user.id,
            }
        )

        views.verify_organization_role(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Organization invitation is not valid.", queue="error")
        ]
        assert db_request.route_path.calls == [pretend.call("manage.organizations")]

    def test_verify_fails_with_token_mismatch(self, db_request, token_service):
        desired_role = "Manager"
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        # Create invitation with a different token than what's in the request
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
            token="WRONG_TOKEN",
        )
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            organization=organization,
            user=owner_user,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.user = user
        db_request.method = "POST"
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.remote_addr = "192.168.1.1"
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-organization-role-verify",
                "desired_role": desired_role,
                "user_id": user.id,
                "organization_id": organization.id,
                "submitter_id": owner_user.id,
            }
        )

        views.verify_organization_role(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Organization invitation is not valid.", queue="error")
        ]
        assert db_request.route_path.calls == [pretend.call("manage.organizations")]

    def test_verify_role_get_confirmation(self, db_request, token_service):
        desired_role = "Manager"
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
            token="RANDOM_KEY",
        )
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            organization=organization,
            user=owner_user,
            role_name=OrganizationRoleType.Owner,
        )

        db_request.user = user
        db_request.method = "GET"
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.remote_addr = "192.168.1.1"
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-organization-role-verify",
                "desired_role": desired_role,
                "user_id": user.id,
                "organization_id": organization.id,
                "submitter_id": owner_user.id,
            }
        )

        roles = views.verify_organization_role(db_request)

        assert roles == {
            "organization_name": organization.name,
            "desired_role": desired_role,
        }


class TestVerifyProjectRole:
    @pytest.mark.parametrize("desired_role", ["Maintainer", "Owner"])
    def test_verify_project_role(
        self, db_request, user_service, token_service, monkeypatch, desired_role
    ):
        project = ProjectFactory.create()
        user = UserFactory.create()
        RoleInvitationFactory.create(user=user, project=project, token="RANDOM_KEY")
        owner_user = UserFactory.create()
        RoleFactory(user=owner_user, project=project, role_name="Owner")

        db_request.user = user
        db_request.method = "POST"
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/")
        db_request.remote_addr = "192.168.1.1"
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-project-role-verify",
                "desired_role": desired_role,
                "user_id": user.id,
                "project_id": project.id,
                "submitter_id": db_request.user.id,
            }
        )
        user_service.get_user = pretend.call_recorder(lambda user_id: user)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        collaborator_added_email = pretend.call_recorder(lambda *args, **kwargs: None)
        monkeypatch.setattr(
            views, "send_collaborator_added_email", collaborator_added_email
        )
        added_as_collaborator_email = pretend.call_recorder(
            lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            views, "send_added_as_collaborator_email", added_as_collaborator_email
        )

        result = views.verify_project_role(db_request)

        db_request.db.flush()

        assert db_request.find_service.calls == [
            pretend.call(ITokenService, name="email"),
            pretend.call(IUserService, context=None),
        ]

        assert token_service.loads.calls == [pretend.call("RANDOM_KEY")]
        assert user_service.get_user.calls == [
            pretend.call(user.id),
            pretend.call(db_request.user.id),
        ]

        assert not (
            db_request.db.query(RoleInvitation)
            .filter(RoleInvitation.user == user)
            .filter(RoleInvitation.project == project)
            .one_or_none()
        )
        assert (
            db_request.db.query(Role)
            .filter(Role.project == project, Role.user == user)
            .one()
        )

        assert db_request.session.flash.calls == [
            pretend.call(
                f"You are now {desired_role} of the '{project.name}' project.",
                queue="success",
            )
        ]

        assert collaborator_added_email.calls == [
            pretend.call(
                db_request,
                {owner_user},
                user=user,
                submitter=db_request.user,
                project_name=project.name,
                role=desired_role,
            )
        ]
        assert added_as_collaborator_email.calls == [
            pretend.call(
                db_request,
                user,
                submitter=db_request.user,
                project_name=project.name,
                role=desired_role,
            )
        ]

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert db_request.route_path.calls == [
            (
                pretend.call("manage.project.roles", project_name=project.name)
                if desired_role == "Owner"
                else pretend.call("packaging.project", name=project.name)
            )
        ]

    @pytest.mark.parametrize(
        ("exception", "message"),
        [
            (TokenInvalid, "Invalid token: request a new project role invitation"),
            (TokenExpired, "Expired token: request a new project role invitation"),
            (TokenMissing, "Invalid token: no token supplied"),
        ],
    )
    def test_verify_project_role_loads_failure(
        self, pyramid_request, exception, message
    ):
        def loads(token):
            raise exception

        pyramid_request.find_service = lambda *a, **kw: pretend.stub(loads=loads)
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.verify_project_role(pyramid_request)

        assert pyramid_request.route_path.calls == [pretend.call("manage.projects")]
        assert pyramid_request.session.flash.calls == [
            pretend.call(message, queue="error")
        ]

    def test_verify_email_invalid_action(self, pyramid_request):
        data = {"action": "invalid-action"}
        pyramid_request.find_service = lambda *a, **kw: pretend.stub(
            loads=lambda a: data
        )
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.verify_project_role(pyramid_request)

        assert pyramid_request.route_path.calls == [pretend.call("manage.projects")]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Invalid token: not a collaboration invitation token", queue="error"
            )
        ]

    def test_verify_project_role_revoked(self, db_request, user_service, token_service):
        project = ProjectFactory.create()
        user = UserFactory.create()

        db_request.user = user
        db_request.method = "POST"
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.remote_addr = "192.168.1.1"
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-project-role-verify",
                "desired_role": "Maintainer",
                "user_id": user.id,
                "project_id": project.id,
                "submitter_id": db_request.user.id,
            }
        )
        user_service.get_user = pretend.call_recorder(lambda user_id: user)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.verify_project_role(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                "Role invitation no longer exists.",
                queue="error",
            )
        ]
        assert db_request.route_path.calls == [pretend.call("manage.projects")]

    def test_verify_project_role_declined(
        self, db_request, user_service, token_service
    ):
        project = ProjectFactory.create()
        user = UserFactory.create()
        RoleInvitationFactory.create(user=user, project=project, token="RANDOM_KEY")

        db_request.user = user
        db_request.method = "POST"
        db_request.POST.update({"token": "RANDOM_KEY", "decline": "Decline"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.remote_addr = "192.168.1.1"
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-project-role-verify",
                "desired_role": "Maintainer",
                "user_id": user.id,
                "project_id": project.id,
                "submitter_id": db_request.user.id,
            }
        )
        user_service.get_user = pretend.call_recorder(lambda user_id: user)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.verify_project_role(db_request)

        assert not (
            db_request.db.query(RoleInvitation)
            .filter(RoleInvitation.user == user)
            .filter(RoleInvitation.project == project)
            .one_or_none()
        )
        assert isinstance(result, HTTPSeeOther)
        assert db_request.route_path.calls == [pretend.call("manage.projects")]

    def test_verify_fails_with_different_user(
        self, db_request, user_service, token_service
    ):
        project = ProjectFactory.create()
        user = UserFactory.create()
        user_2 = UserFactory.create()

        db_request.user = user_2
        db_request.method = "POST"
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.remote_addr = "192.168.1.1"
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-project-role-verify",
                "desired_role": "Maintainer",
                "user_id": user.id,
                "project_id": project.id,
                "submitter_id": db_request.user.id,
            }
        )
        user_service.get_user = pretend.call_recorder(lambda user_id: user)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.verify_project_role(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Role invitation is not valid.", queue="error")
        ]
        assert db_request.route_path.calls == [pretend.call("manage.projects")]

    def test_verify_fails_with_token_mismatch(
        self, db_request, user_service, token_service
    ):
        project = ProjectFactory.create()
        user = UserFactory.create()
        # Create invitation with a different token than what's in the request
        RoleInvitationFactory.create(user=user, project=project, token="WRONG_TOKEN")

        db_request.user = user
        db_request.method = "POST"
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.remote_addr = "192.168.1.1"
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-project-role-verify",
                "desired_role": "Maintainer",
                "user_id": user.id,
                "project_id": project.id,
                "submitter_id": db_request.user.id,
            }
        )
        user_service.get_user = pretend.call_recorder(lambda user_id: user)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.verify_project_role(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Role invitation is not valid.", queue="error")
        ]
        assert db_request.route_path.calls == [pretend.call("manage.projects")]

    def test_verify_fails_with_missing_project(
        self, db_request, user_service, token_service
    ):
        project = ProjectFactory.create()
        user = UserFactory.create()

        db_request.user = user
        db_request.method = "POST"
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.remote_addr = "192.168.1.1"
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-project-role-verify",
                "desired_role": "Maintainer",
                "user_id": user.id,
                "project_id": project.id,
                "submitter_id": db_request.user.id,
            }
        )
        user_service.get_user = pretend.call_recorder(lambda user_id: user)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        db_request.db.delete(project)

        views.verify_project_role(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Invalid token: project does not exist", queue="error")
        ]
        assert db_request.route_path.calls == [pretend.call("manage.projects")]

    def test_verify_role_get_confirmation(
        self, db_request, user_service, token_service
    ):
        project = ProjectFactory.create()
        user = UserFactory.create()
        RoleInvitationFactory.create(user=user, project=project, token="RANDOM_KEY")

        db_request.user = user
        db_request.method = "GET"
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.remote_addr = "192.168.1.1"
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "email-project-role-verify",
                "desired_role": "Maintainer",
                "user_id": user.id,
                "project_id": project.id,
                "submitter_id": db_request.user.id,
            }
        )
        user_service.get_user = pretend.call_recorder(lambda user_id: user)
        db_request.find_service = pretend.call_recorder(
            lambda iface, context=None, name=None: {
                ITokenService: token_service,
                IUserService: user_service,
            }.get(iface)
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        roles = views.verify_project_role(db_request)

        assert roles == {
            "project_name": project.name,
            "desired_role": "Maintainer",
        }


class TestViewTermsOfService:
    def test_view_terms_of_service_no_user(self):
        user_service = pretend.stub(
            record_tos_engagement=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request = pretend.stub(
            user=None,
            find_service=lambda *a, **kw: user_service,
            registry=pretend.stub(settings={"terms.revision": "the-revision"}),
        )
        result = views.view_terms_of_service(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert (
            result.headers["Location"]
            == "https://policies.python.org/pypi.org/Terms-of-Service/"
        )
        assert user_service.record_tos_engagement.calls == []

    def test_view_terms_of_service(self):
        user_service = pretend.stub(
            record_tos_engagement=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request = pretend.stub(
            user=pretend.stub(id="user-id"),
            find_service=lambda *a, **kw: user_service,
            registry=pretend.stub(settings={"terms.revision": "the-revision"}),
        )
        result = views.view_terms_of_service(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert (
            result.headers["Location"]
            == "https://policies.python.org/pypi.org/Terms-of-Service/"
        )
        assert user_service.record_tos_engagement.calls == [
            pretend.call("user-id", "the-revision", TermsOfServiceEngagement.Viewed)
        ]


class TestProfileCallout:
    def test_profile_callout_returns_user(self):
        user = pretend.stub()
        request = pretend.stub()

        assert views.profile_callout(user, request) == {"user": user}


class TestEditProfileButton:
    def test_edit_profile_button(self):
        user = pretend.stub()
        request = pretend.stub()

        assert views.edit_profile_button(user, request) == {"user": user}


class TestProfilePublicEmail:
    def test_profile_public_email_returns_user(self):
        user = pretend.stub()
        request = pretend.stub()

        assert views.profile_public_email(user, request) == {"user": user}


class TestReAuthentication:
    @pytest.mark.parametrize("next_route", [None, "/manage/accounts", "/projects/"])
    def test_reauth(self, monkeypatch, pyramid_request, pyramid_services, next_route):
        user_service = pretend.stub(get_password_timestamp=lambda uid: 0)
        response = pretend.stub()

        monkeypatch.setattr(views, "HTTPSeeOther", lambda url: response)

        pyramid_services.register_service(user_service, IUserService, None)

        pyramid_request.route_path = lambda *args, **kwargs: pretend.stub()
        pyramid_request.session.record_auth_timestamp = pretend.call_recorder(
            lambda *args: None
        )
        pyramid_request.session.record_password_timestamp = lambda ts: None
        pyramid_request.user = pretend.stub(id=pretend.stub, username=pretend.stub())
        pyramid_request.matched_route = pretend.stub(name=pretend.stub())
        pyramid_request.matchdict = {"foo": "bar"}
        pyramid_request.GET = pretend.stub(mixed=lambda: {"baz": "bar"})

        form_obj = pretend.stub(
            next_route=pretend.stub(data=next_route),
            next_route_matchdict=pretend.stub(data="{}"),
            next_route_query=pretend.stub(data="{}"),
            validate=lambda: True,
        )
        form_class = pretend.call_recorder(lambda d, **kw: form_obj)

        if next_route is not None:
            pyramid_request.method = "POST"
            pyramid_request.POST["next_route"] = next_route
            pyramid_request.POST["next_route_matchdict"] = "{}"
            pyramid_request.POST["next_route_query"] = "{}"

        _ = views.reauthenticate(pyramid_request, _form_class=form_class)

        assert pyramid_request.session.record_auth_timestamp.calls == (
            [pretend.call()] if next_route is not None else []
        )
        assert form_class.calls == [
            pretend.call(
                pyramid_request.POST,
                request=pyramid_request,
                user_id=pyramid_request.user.id,
                next_route=pyramid_request.matched_route.name,
                next_route_matchdict=json.dumps(pyramid_request.matchdict),
                next_route_query=json.dumps(pyramid_request.GET.mixed()),
                action="reauthenticate",
                user_service=user_service,
                check_password_metrics_tags=[
                    "method:reauth",
                    "auth_method:reauthenticate_form",
                ],
            )
        ]

    def test_reauth_no_user(self, monkeypatch, pyramid_request):
        pyramid_request.user = None
        pyramid_request.route_path = pretend.call_recorder(lambda a: "/the-redirect")

        result = views.reauthenticate(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert pyramid_request.route_path.calls == [pretend.call("accounts.login")]
        assert result.headers["Location"] == "/the-redirect"

    def test_reauth_rejects_different_users_password(
        self, monkeypatch, pyramid_request, pyramid_services
    ):
        alice = pretend.stub(
            id=1,
            username="alice",
            record_event=pretend.call_recorder(lambda **kwargs: None),
        )
        user_service = pretend.stub(
            check_password=pretend.call_recorder(
                lambda user_id, password, tags=None: (
                    user_id == 2 and password == "bob-password"
                )
            ),
            find_userid=pretend.call_recorder(lambda username: 2),
            get_user=pretend.call_recorder(lambda user_id: alice),
            get_password_timestamp=pretend.call_recorder(lambda user_id: 0),
        )
        response = pretend.stub(headers={"Location": "/target"})

        monkeypatch.setattr(views, "HTTPSeeOther", lambda url: response)
        pyramid_services.register_service(user_service, IUserService, None)

        pyramid_request.method = "POST"
        pyramid_request.POST = MultiDict(
            {
                "username": "bob",
                "password": "bob-password",
                "next_route": "manage.account.publishing",
                "next_route_matchdict": "{}",
                "next_route_query": "{}",
            }
        )
        pyramid_request.user = alice
        pyramid_request.matched_route = pretend.stub(name="manage.account.publishing")
        pyramid_request.matchdict = {}
        pyramid_request.GET = pretend.stub(mixed=lambda: {})
        pyramid_request.route_path = pretend.call_recorder(lambda *a, **kw: "/target")
        pyramid_request.session.record_auth_timestamp = pretend.call_recorder(
            lambda: None
        )
        pyramid_request.session.record_password_timestamp = pretend.call_recorder(
            lambda ts: None
        )

        result = views.reauthenticate(pyramid_request)

        assert result is response
        assert user_service.check_password.calls == [
            pretend.call(
                alice.id,
                "bob-password",
                tags=[
                    "method:reauth",
                    "auth_method:reauthenticate_form",
                ],
            )
        ]
        assert user_service.find_userid.calls == []
        assert alice.record_event.calls == [
            pretend.call(
                tag="account:reauthenticate:failure",
                request=pyramid_request,
                additional={"reason": "invalid_password"},
            )
        ]
        assert pyramid_request.session.record_auth_timestamp.calls == []
        assert pyramid_request.session.record_password_timestamp.calls == []

    @pytest.mark.parametrize(
        ("next_route_matchdict", "next_route_query"),
        [
            ("invalid_json", "{}"),
            ("{}", "invalid_json"),
            ("{'single': 'quotes'}", "{}"),
            ("123", "{}"),
            ("{}", "123"),
            ("[1, 2]", "{}"),
            ("{}", "[1, 2]"),
            ("true", "{}"),
            ("{}", '"string"'),
        ],
    )
    def test_reauth_invalid_json_raises_400(
        self, pyramid_request, pyramid_services, next_route_matchdict, next_route_query
    ):
        user_service = pretend.stub()
        pyramid_services.register_service(user_service, IUserService, None)

        pyramid_request.user = pretend.stub(id=pretend.stub(), username=pretend.stub())
        pyramid_request.matched_route = pretend.stub(name=pretend.stub())
        pyramid_request.matchdict = {}
        pyramid_request.GET = pretend.stub(mixed=lambda: {})
        pyramid_request.route_path = pretend.call_recorder(lambda *a, **kw: "/target")

        form_obj = pretend.stub(
            next_route=pretend.stub(data="/manage/accounts"),
            next_route_matchdict=pretend.stub(data=next_route_matchdict),
            next_route_query=pretend.stub(data=next_route_query),
            validate=lambda: True,
        )
        form_class = pretend.call_recorder(lambda d, **kw: form_obj)

        with pytest.raises(HTTPBadRequest):
            views.reauthenticate(pyramid_request, _form_class=form_class)


class TestManageAccountPublishingViews:
    def test_initializes(self, metrics):
        project_service = pretend.stub(check_project_name=lambda name: None)

        def find_service(iface, name=None, context=None):
            if iface is IMetricsService:
                return metrics
            if iface is IProjectService:
                return project_service
            pytest.fail(f"Unexpected service requested: {iface}")

        request = pretend.stub(
            find_service=pretend.call_recorder(find_service),
            route_url=pretend.stub(),
            POST=MultiDict(),
            user=pretend.stub(id=pretend.stub()),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                }
            ),
        )
        view = views.ManageAccountPublishingViews(request)

        assert view.request is request
        assert view.metrics is metrics
        assert view.project_service is project_service

        assert view.request.find_service.calls == [
            pretend.call(IMetricsService, context=None),
            pretend.call(IProjectService, context=None),
        ]

    @pytest.mark.parametrize(
        ("ip_exceeded", "user_exceeded"),
        [
            (False, False),
            (False, True),
            (True, False),
        ],
    )
    def test_ratelimiting(self, metrics, ip_exceeded, user_exceeded):
        user_rate_limiter = pretend.stub(
            hit=pretend.call_recorder(lambda *a, **kw: None),
            test=pretend.call_recorder(lambda uid: not user_exceeded),
            resets_in=pretend.call_recorder(lambda uid: pretend.stub()),
        )
        ip_rate_limiter = pretend.stub(
            hit=pretend.call_recorder(lambda *a, **kw: None),
            test=pretend.call_recorder(lambda ip: not ip_exceeded),
            resets_in=pretend.call_recorder(lambda uid: pretend.stub()),
        )

        def find_service(iface, name=None, context=None):
            if iface is IMetricsService:
                return metrics
            if iface is IProjectService:
                return pretend.stub(check_project_name=lambda name: None)

            if name == "user_oidc.publisher.register":
                return user_rate_limiter
            return ip_rate_limiter

        request = pretend.stub(
            find_service=pretend.call_recorder(find_service),
            user=pretend.stub(id=pretend.stub()),
            remote_addr=pretend.stub(),
            POST=MultiDict(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                }
            ),
            route_url=pretend.stub(),
        )

        view = views.ManageAccountPublishingViews(request)

        assert view._ratelimiters == {
            "user.oidc": user_rate_limiter,
            "ip.oidc": ip_rate_limiter,
        }
        assert request.find_service.calls == [
            pretend.call(IMetricsService, context=None),
            pretend.call(IProjectService, context=None),
            pretend.call(IRateLimiter, name="user_oidc.publisher.register"),
            pretend.call(IRateLimiter, name="ip_oidc.publisher.register"),
        ]

        view._hit_ratelimits()

        assert user_rate_limiter.hit.calls == [
            pretend.call(request.user.id),
        ]
        assert ip_rate_limiter.hit.calls == [pretend.call(request.remote_addr)]

        if user_exceeded or ip_exceeded:
            with pytest.raises(TooManyOIDCRegistrations):
                view._check_ratelimits()
        else:
            view._check_ratelimits()

    def test_manage_publishing(self, metrics, monkeypatch):
        route_url = pretend.stub()
        request = pretend.stub(
            user=pretend.stub(id=pretend.stub()),
            route_url=route_url,
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                }
            ),
            find_service=lambda svc, **kw: {
                IMetricsService: metrics,
                IProjectService: project_service,
            }[svc],
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            db=pretend.stub(scalars=lambda *a, **kw: pretend.stub(all=lambda: [])),
            POST=pretend.stub(),
        )

        project_service = pretend.stub(check_project_name=lambda name: None)

        pending_github_publisher_form_obj = pretend.stub()
        pending_github_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_github_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGitHubPublisherForm", pending_github_publisher_form_cls
        )
        pending_gitlab_publisher_form_obj = pretend.stub()
        pending_gitlab_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_gitlab_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGitLabPublisherForm", pending_gitlab_publisher_form_cls
        )
        pending_google_publisher_form_obj = pretend.stub()
        pending_google_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_google_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGooglePublisherForm", pending_google_publisher_form_cls
        )
        pending_activestate_publisher_form_obj = pretend.stub()
        pending_activestate_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_activestate_publisher_form_obj
        )
        monkeypatch.setattr(
            views,
            "PendingActiveStatePublisherForm",
            pending_activestate_publisher_form_cls,
        )

        view = views.ManageAccountPublishingViews(request)

        assert view.manage_publishing() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
            },
            "project_names_with_publishers": [],
            "pending_github_publisher_form": pending_github_publisher_form_obj,
            "pending_gitlab_publisher_form": pending_gitlab_publisher_form_obj,
            "pending_google_publisher_form": pending_google_publisher_form_obj,
            "pending_activestate_publisher_form": pending_activestate_publisher_form_obj,  # noqa: E501
        }

        assert request.flags.disallow_oidc.calls == [
            pretend.call(),
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
        ]
        assert pending_github_publisher_form_cls.calls == [
            pretend.call(
                request.POST,
                api_token="fake-api-token",
                route_url=route_url,
                check_project_name=project_service.check_project_name,
                user=request.user,
            )
        ]
        assert pending_gitlab_publisher_form_cls.calls == [
            pretend.call(
                request.POST,
                route_url=route_url,
                check_project_name=project_service.check_project_name,
                user=request.user,
            )
        ]

    def test_manage_publishing_admin_disabled(self, monkeypatch, pyramid_request):
        project_service = pretend.stub(check_project_name=lambda name: None)
        pyramid_request.find_service = lambda _, **kw: project_service

        pyramid_request.user = pretend.stub(id=pretend.stub())
        pyramid_request.db = pretend.stub(
            scalars=lambda *a, **kw: pretend.stub(all=lambda: [])
        )
        pyramid_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        pyramid_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: True)
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        pending_github_publisher_form_obj = pretend.stub()
        pending_github_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_github_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGitHubPublisherForm", pending_github_publisher_form_cls
        )
        pending_gitlab_publisher_form_obj = pretend.stub()
        pending_gitlab_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_gitlab_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGitLabPublisherForm", pending_gitlab_publisher_form_cls
        )
        pending_google_publisher_form_obj = pretend.stub()
        pending_google_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_google_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGooglePublisherForm", pending_google_publisher_form_cls
        )
        pending_activestate_publisher_form_obj = pretend.stub()
        pending_activestate_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_activestate_publisher_form_obj
        )
        monkeypatch.setattr(
            views,
            "PendingActiveStatePublisherForm",
            pending_activestate_publisher_form_cls,
        )

        view = views.ManageAccountPublishingViews(pyramid_request)

        assert view.manage_publishing() == {
            "disabled": {
                "GitHub": True,
                "GitLab": True,
                "Google": True,
                "ActiveState": True,
            },
            "project_names_with_publishers": [],
            "pending_github_publisher_form": pending_github_publisher_form_obj,
            "pending_gitlab_publisher_form": pending_gitlab_publisher_form_obj,
            "pending_google_publisher_form": pending_google_publisher_form_obj,
            "pending_activestate_publisher_form": pending_activestate_publisher_form_obj,  # noqa: E501
        }

        assert pyramid_request.flags.disallow_oidc.calls == [
            pretend.call(),
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                (
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]
        assert pending_github_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                api_token="fake-api-token",
                route_url=pyramid_request.route_url,
                check_project_name=project_service.check_project_name,
                user=pyramid_request.user,
            )
        ]
        assert pending_gitlab_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                route_url=pyramid_request.route_url,
                check_project_name=project_service.check_project_name,
                user=pyramid_request.user,
            )
        ]

    @pytest.mark.parametrize(
        ("view_name", "flag", "publisher_name"),
        [
            (
                "add_pending_github_oidc_publisher",
                AdminFlagValue.DISALLOW_GITHUB_OIDC,
                "GitHub",
            ),
            (
                "add_pending_gitlab_oidc_publisher",
                AdminFlagValue.DISALLOW_GITLAB_OIDC,
                "GitLab",
            ),
            (
                "add_pending_google_oidc_publisher",
                AdminFlagValue.DISALLOW_GOOGLE_OIDC,
                "Google",
            ),
            (
                "add_pending_activestate_oidc_publisher",
                AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC,
                "ActiveState",
            ),
        ],
    )
    def test_add_pending_oidc_publisher_admin_disabled(
        self, monkeypatch, pyramid_request, view_name, flag, publisher_name
    ):
        project_service = pretend.stub(check_project_name=lambda name: None)
        pyramid_request.find_service = lambda interface, **kwargs: {
            IProjectService: project_service,
            IMetricsService: pretend.stub(),
        }[interface]

        pyramid_request.user = pretend.stub(id=pretend.stub())
        pyramid_request.db = pretend.stub(
            scalars=lambda *a, **kw: pretend.stub(all=lambda: [])
        )
        pyramid_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        pyramid_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: True),
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        pending_github_publisher_form_obj = pretend.stub()
        pending_github_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_github_publisher_form_obj
        )
        monkeypatch.setattr(
            views,
            "PendingGitHubPublisherForm",
            pending_github_publisher_form_cls,
        )
        pending_activestate_publisher_form_obj = pretend.stub()
        pending_activestate_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_activestate_publisher_form_obj
        )
        monkeypatch.setattr(
            views,
            "PendingActiveStatePublisherForm",
            pending_activestate_publisher_form_cls,
        )
        pending_gitlab_publisher_form_obj = pretend.stub()
        pending_gitlab_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_gitlab_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGitLabPublisherForm", pending_gitlab_publisher_form_cls
        )
        pending_google_publisher_form_obj = pretend.stub()
        pending_google_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_google_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGooglePublisherForm", pending_google_publisher_form_cls
        )

        view = views.ManageAccountPublishingViews(pyramid_request)

        assert getattr(view, view_name)() == {
            "disabled": {
                "GitHub": True,
                "GitLab": True,
                "Google": True,
                "ActiveState": True,
            },
            "project_names_with_publishers": [],
            "pending_github_publisher_form": pending_github_publisher_form_obj,
            "pending_gitlab_publisher_form": pending_gitlab_publisher_form_obj,
            "pending_google_publisher_form": pending_google_publisher_form_obj,
            "pending_activestate_publisher_form": pending_activestate_publisher_form_obj,  # noqa: E501
        }

        assert pyramid_request.flags.disallow_oidc.calls == [
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
            pretend.call(flag),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                (
                    f"{publisher_name}-based trusted publishing is temporarily "
                    "disabled. See https://pypi.org/help#admin-intervention for "
                    "details."
                ),
                queue="error",
            )
        ]
        assert pending_github_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                api_token="fake-api-token",
                route_url=pyramid_request.route_url,
                check_project_name=project_service.check_project_name,
                user=pyramid_request.user,
            )
        ]
        assert pending_gitlab_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                route_url=pyramid_request.route_url,
                check_project_name=project_service.check_project_name,
                user=pyramid_request.user,
            )
        ]

    @pytest.mark.parametrize(
        ("view_name", "flag", "publisher_name"),
        [
            (
                "add_pending_github_oidc_publisher",
                AdminFlagValue.DISALLOW_GITHUB_OIDC,
                "GitHub",
            ),
            (
                "add_pending_gitlab_oidc_publisher",
                AdminFlagValue.DISALLOW_GITLAB_OIDC,
                "GitLab",
            ),
            (
                "add_pending_google_oidc_publisher",
                AdminFlagValue.DISALLOW_GOOGLE_OIDC,
                "Google",
            ),
            (
                "add_pending_activestate_oidc_publisher",
                AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC,
                "ActiveState",
            ),
        ],
    )
    def test_add_pending_oidc_publisher_user_cannot_register(
        self,
        monkeypatch,
        pyramid_request,
        view_name,
        flag,
        publisher_name,
        metrics,
    ):
        project_service = pretend.stub(check_project_name=lambda name: None)
        pyramid_request.find_service = lambda interface, **kwargs: {
            IProjectService: project_service,
            IMetricsService: metrics,
        }[interface]

        pyramid_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        pyramid_request.user = pretend.stub(
            has_primary_verified_email=False,
            id=pretend.stub(),
        )
        pyramid_request.db = pretend.stub(
            scalars=lambda *a, **kw: pretend.stub(all=lambda: [])
        )
        pyramid_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False),
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        pending_github_publisher_form_obj = pretend.stub()
        pending_github_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_github_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGitHubPublisherForm", pending_github_publisher_form_cls
        )
        pending_gitlab_publisher_form_obj = pretend.stub()
        pending_gitlab_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_gitlab_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGitLabPublisherForm", pending_gitlab_publisher_form_cls
        )
        pending_google_publisher_form_obj = pretend.stub()
        pending_google_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_google_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGooglePublisherForm", pending_google_publisher_form_cls
        )
        pending_activestate_publisher_form_obj = pretend.stub()
        pending_activestate_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_activestate_publisher_form_obj
        )
        monkeypatch.setattr(
            views,
            "PendingActiveStatePublisherForm",
            pending_activestate_publisher_form_cls,
        )

        view = views.ManageAccountPublishingViews(pyramid_request)

        assert getattr(view, view_name)() == {
            "disabled": {
                "GitHub": False,
                "GitLab": False,
                "Google": False,
                "ActiveState": False,
            },
            "project_names_with_publishers": [],
            "pending_github_publisher_form": pending_github_publisher_form_obj,
            "pending_gitlab_publisher_form": pending_gitlab_publisher_form_obj,
            "pending_google_publisher_form": pending_google_publisher_form_obj,
            "pending_activestate_publisher_form": pending_activestate_publisher_form_obj,  # noqa: E501
        }

        assert pyramid_request.flags.disallow_oidc.calls == [
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
            pretend.call(flag),
        ]
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_pending_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                (
                    "You must have a verified email in order to register a "
                    "pending trusted publisher. "
                    "See https://pypi.org/help#openid-connect for details."
                ),
                queue="error",
            )
        ]
        assert pending_github_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                api_token="fake-api-token",
                route_url=pyramid_request.route_url,
                check_project_name=project_service.check_project_name,
                user=pyramid_request.user,
            )
        ]
        assert pending_gitlab_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                route_url=pyramid_request.route_url,
                check_project_name=project_service.check_project_name,
                user=pyramid_request.user,
            )
        ]

    @pytest.mark.parametrize(
        ("view_name", "flag", "publisher_name", "make_publisher", "publisher_class"),
        [
            (
                "add_pending_github_oidc_publisher",
                AdminFlagValue.DISALLOW_GITHUB_OIDC,
                "GitHub",
                lambda i, user_id: PendingGitHubPublisher(
                    project_name="some-project-name-" + str(i),
                    repository_name="some-repository" + str(i),
                    repository_owner="some-owner",
                    repository_owner_id="some-id",
                    workflow_filename="some-filename",
                    environment="",
                    added_by_id=user_id,
                ),
                PendingGitHubPublisher,
            ),
            (
                "add_pending_gitlab_oidc_publisher",
                AdminFlagValue.DISALLOW_GITLAB_OIDC,
                "GitLab",
                lambda i, user_id: PendingGitLabPublisher(
                    project_name="some-project-name-" + str(i),
                    project="some-repository" + str(i),
                    namespace="some-namespace",
                    workflow_filepath="some-filepath",
                    environment="",
                    issuer_url="https://gitlab.com",
                    added_by_id=user_id,
                ),
                PendingGitLabPublisher,
            ),
            (
                "add_pending_google_oidc_publisher",
                AdminFlagValue.DISALLOW_GOOGLE_OIDC,
                "Google",
                lambda i, user_id: PendingGooglePublisher(
                    project_name="some-project-name-" + str(i),
                    email="some-email-" + str(i) + "@example.com",
                    sub="some-sub",
                    added_by_id=user_id,
                ),
                PendingGooglePublisher,
            ),
            (
                "add_pending_activestate_oidc_publisher",
                AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC,
                "ActiveState",
                lambda i, user_id: PendingActiveStatePublisher(
                    project_name="some-project-name-" + str(i),
                    added_by_id=user_id,
                    organization="some-org-" + str(i),
                    activestate_project_name="some-project-" + str(i),
                    actor="some-user-" + str(i),
                    actor_id="some-user-id-" + str(i),
                ),
                PendingActiveStatePublisher,
            ),
        ],
    )
    def test_add_pending_github_oidc_publisher_too_many_already(
        self,
        monkeypatch,
        db_request,
        view_name,
        flag,
        publisher_name,
        make_publisher,
        publisher_class,
    ):
        db_request.user = UserFactory.create()
        EmailFactory(user=db_request.user, verified=True, primary=True)
        for i in range(3):
            pending_publisher = make_publisher(i, db_request.user.id)
            db_request.db.add(pending_publisher)

        db_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict(
            {
                "owner": "some-owner",
                "repository": "some-repository",
                "workflow_filename": "some-workflow-filename.yml",
                "environment": "some-environment",
                "project_name": "some-other-project-name",
            }
        )

        view = views.ManageAccountPublishingViews(db_request)

        assert getattr(view, view_name)() == view.default_response
        assert db_request.flags.disallow_oidc.calls == [
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
            pretend.call(flag),
        ]
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_pending_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "You can't register more than 3 pending trusted publishers at once.",
                queue="error",
            )
        ]
        assert len(db_request.db.query(publisher_class).all()) == 3

    @pytest.mark.parametrize(
        ("view_name", "publisher_name"),
        [
            (
                "add_pending_github_oidc_publisher",
                "GitHub",
            ),
            (
                "add_pending_gitlab_oidc_publisher",
                "GitLab",
            ),
            (
                "add_pending_google_oidc_publisher",
                "Google",
            ),
            (
                "add_pending_activestate_oidc_publisher",
                "ActiveState",
            ),
        ],
    )
    def test_add_pending_oidc_publisher_ratelimited(
        self, monkeypatch, pyramid_request, view_name, publisher_name
    ):
        pyramid_request.user = pretend.stub(
            has_primary_verified_email=True,
            pending_oidc_publishers=[],
            id=pretend.stub(),
        )
        pyramid_request.db = pretend.stub(
            scalars=lambda *a, **kw: pretend.stub(all=lambda: [])
        )
        pyramid_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        pyramid_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.POST = MultiDict(
            {
                "owner": "some-owner",
                "repository": "some-repository",
                "workflow_filename": "some-workflow-filename.yml",
                "environment": "some-environment",
                "project_name": "some-other-project-name",
            }
        )

        view = views.ManageAccountPublishingViews(pyramid_request)
        monkeypatch.setattr(
            view,
            "_check_ratelimits",
            pretend.call_recorder(
                pretend.raiser(
                    TooManyOIDCRegistrations(
                        resets_in=pretend.stub(total_seconds=lambda: 60)
                    )
                )
            ),
        )

        assert isinstance(getattr(view, view_name)(), HTTPTooManyRequests)
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_pending_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
            pretend.call(
                "warehouse.oidc.add_pending_publisher.ratelimited",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]

    @pytest.mark.parametrize(
        ("view_name", "publisher_name"),
        [
            (
                "add_pending_github_oidc_publisher",
                "GitHub",
            ),
            (
                "add_pending_gitlab_oidc_publisher",
                "GitLab",
            ),
            (
                "add_pending_google_oidc_publisher",
                "Google",
            ),
            (
                "add_pending_activestate_oidc_publisher",
                "ActiveState",
            ),
        ],
    )
    def test_add_pending_oidc_publisher_invalid_form(
        self, monkeypatch, db_request, view_name, publisher_name
    ):
        db_request.user = pretend.stub(
            has_primary_verified_email=True,
            pending_oidc_publishers=[],
            id=uuid.uuid4(),
        )
        db_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict(
            {
                "owner": "some-owner",
                "repository": "some-repository",
                "workflow_filename": "some-workflow-filename-without-extension",  # Fail
                "environment": "some-environment",
                "project_name": "some-other-project-name",
            }
        )

        view = views.ManageAccountPublishingViews(db_request)

        monkeypatch.setattr(
            views.ManageAccountPublishingViews,
            "default_response",
            view.default_response,
        )
        monkeypatch.setattr(
            views.PendingGitHubPublisherForm,
            "_lookup_owner",
            lambda *a: {"login": "some-owner", "id": "some-owner-id"},
        )
        monkeypatch.setattr(
            views.PendingGitHubPublisherForm,
            "validate_project_name",
            lambda *a: True,
        )

        monkeypatch.setattr(
            views.PendingActiveStatePublisherForm,
            "_lookup_organization",
            lambda *a: None,
        )

        monkeypatch.setattr(
            views.PendingActiveStatePublisherForm,
            "_lookup_actor",
            lambda *a: {"user_id": "some-user-id"},
        )

        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert getattr(view, view_name)() == view.default_response
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_pending_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]

    @pytest.mark.parametrize(
        ("view_name", "publisher_name", "make_publisher", "post_body"),
        [
            (
                "add_pending_github_oidc_publisher",
                "GitHub",
                lambda user_id: PendingGitHubPublisher(
                    project_name="some-project-name",
                    repository_name="some-repository",
                    repository_owner="some-owner",
                    repository_owner_id="some-owner-id",
                    workflow_filename="some-workflow-filename.yml",
                    environment="some-environment",
                    added_by_id=user_id,
                ),
                MultiDict(
                    {
                        "owner": "some-owner",
                        "repository": "some-repository",
                        "workflow_filename": "some-workflow-filename.yml",
                        "environment": "some-environment",
                        "project_name": "some-project-name",
                    }
                ),
            ),
            (
                "add_pending_gitlab_oidc_publisher",
                "GitLab",
                lambda user_id: PendingGitLabPublisher(
                    project_name="some-project-name",
                    namespace="some-owner",
                    project="some-repository",
                    workflow_filepath="subfolder/some-workflow-filename.yml",
                    environment="some-environment",
                    issuer_url="https://gitlab.com",
                    added_by_id=user_id,
                ),
                MultiDict(
                    {
                        "namespace": "some-owner",
                        "project": "some-repository",
                        "workflow_filepath": "subfolder/some-workflow-filename.yml",
                        "environment": "some-environment",
                        "project_name": "some-project-name",
                        "issuer_url": "https://gitlab.com",
                    }
                ),
            ),
            (
                "add_pending_google_oidc_publisher",
                "Google",
                lambda user_id: PendingGooglePublisher(
                    project_name="some-project-name",
                    email="some-email@example.com",
                    sub="some-sub",
                    added_by_id=user_id,
                ),
                MultiDict(
                    {
                        "email": "some-email@example.com",
                        "sub": "some-sub",
                        "project_name": "some-project-name",
                    }
                ),
            ),
            (
                "add_pending_activestate_oidc_publisher",
                "ActiveState",
                lambda user_id: PendingActiveStatePublisher(
                    project_name="some-project-name",
                    added_by_id=user_id,
                    organization="some-org",
                    activestate_project_name="some-project",
                    actor="some-user",
                    actor_id="some-user-id",
                ),
                MultiDict(
                    {
                        "organization": "some-org",
                        "project": "some-project",
                        "actor": "some-user",
                        "project_name": "some-project-name",
                    }
                ),
            ),
        ],
    )
    def test_add_pending_oidc_publisher_already_exists(
        self,
        monkeypatch,
        db_request,
        view_name,
        publisher_name,
        make_publisher,
        post_body,
    ):
        db_request.user = UserFactory.create()
        EmailFactory(user=db_request.user, verified=True, primary=True)
        pending_publisher = make_publisher(db_request.user.id)
        db_request.db.add(pending_publisher)
        db_request.db.flush()  # To get it into the DB

        db_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = post_body

        view = views.ManageAccountPublishingViews(db_request)

        monkeypatch.setattr(
            views.ManageAccountPublishingViews,
            "default_response",
            view.default_response,
        )
        monkeypatch.setattr(
            views.PendingGitHubPublisherForm,
            "_lookup_owner",
            lambda *a: {"login": "some-owner", "id": "some-owner-id"},
        )

        monkeypatch.setattr(
            views.PendingActiveStatePublisherForm,
            "_lookup_organization",
            lambda *a: None,
        )

        monkeypatch.setattr(
            views.PendingActiveStatePublisherForm,
            "_lookup_actor",
            lambda *a: {"user_id": "some-user-id"},
        )

        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert getattr(view, view_name)() == view.default_response

        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_pending_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]
        assert db_request.session.flash.calls == [
            pretend.call(
                (
                    "This trusted publisher has already been registered. "
                    "Please contact PyPI's admins if this wasn't intentional."
                ),
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        (
            "view_name",
            "publisher_name",
            "publisher_class",
            "make_publisher",
            "post_body",
        ),
        [
            (
                "add_pending_github_oidc_publisher",
                "GitHub",
                PendingGitHubPublisher,
                lambda user_id: PendingGitHubPublisher(
                    project_name="some-other-project-name",
                    repository_name="some-repository",
                    repository_owner="some-owner",
                    repository_owner_id="some-owner-id",
                    workflow_filename="some-workflow-filename.yml",
                    environment="some-environment",
                    added_by_id=user_id,
                ),
                MultiDict(
                    {
                        "owner": "some-owner",
                        "repository": "some-repository",
                        "workflow_filename": "some-workflow-filename.yml",
                        "environment": "some-environment",
                        "project_name": "some-project-name",
                    }
                ),
            ),
            (
                "add_pending_gitlab_oidc_publisher",
                "GitLab",
                PendingGitLabPublisher,
                lambda user_id: PendingGitLabPublisher(
                    project_name="some-other-project-name",
                    namespace="some-owner",
                    project="some-repository",
                    workflow_filepath="subfolder/some-workflow-filename.yml",
                    environment="some-environment",
                    issuer_url="https://gitlab.com",
                    added_by_id=user_id,
                ),
                MultiDict(
                    {
                        "namespace": "some-owner",
                        "project": "some-repository",
                        "workflow_filepath": "subfolder/some-workflow-filename.yml",
                        "environment": "some-environment",
                        "project_name": "some-project-name",
                        "issuer_url": "https://gitlab.com",
                    }
                ),
            ),
            (
                "add_pending_google_oidc_publisher",
                "Google",
                PendingGooglePublisher,
                lambda user_id: PendingGooglePublisher(
                    project_name="some-other-project-name",
                    email="some-email@example.com",
                    sub="some-sub",
                    added_by_id=user_id,
                ),
                MultiDict(
                    {
                        "email": "some-email@example.com",
                        "sub": "some-sub",
                        "project_name": "some-project-name",
                    }
                ),
            ),
            (
                "add_pending_activestate_oidc_publisher",
                "ActiveState",
                PendingActiveStatePublisher,
                lambda user_id: PendingActiveStatePublisher(
                    project_name="some-other-project-name",
                    added_by_id=user_id,
                    organization="some-org",
                    activestate_project_name="some-project",
                    actor="some-user",
                    actor_id="some-user-id",
                ),
                MultiDict(
                    {
                        "organization": "some-org",
                        "project": "some-project",
                        "actor": "some-user",
                        "project_name": "some-project-name",
                    }
                ),
            ),
        ],
    )
    def test_add_pending_oidc_publisher_uniqueviolation(
        self,
        monkeypatch,
        db_request,
        view_name,
        publisher_name,
        publisher_class,
        make_publisher,
        post_body,
    ):
        """A UniqueViolation raised by the INSERT during ``flush()`` means
        another pending publisher already exists for the same external
        identity tuple but with a different ``project_name``. The early
        duplicate-check query keys on ``project_name`` so it misses that row,
        but the DB unique constraint does not, so the insert fails.

        Surface the conflict to the user instead of silently redirecting as if
        the registration succeeded -- and crucially, roll back the now-aborted
        transaction so the session stays usable for the rest of the request
        (template rendering, the end-of-request commit). Regression test for
        GH-20006.
        """
        db_request.user = UserFactory.create()
        EmailFactory(user=db_request.user, verified=True, primary=True)
        # A pending publisher with the same external identity but a *different*
        # project_name. flush()-ing it sends the INSERT to the DB so the next
        # conflicting insert raises a real UniqueViolation.
        existing_publisher = make_publisher(db_request.user.id)
        db_request.db.add(existing_publisher)
        db_request.db.flush()

        db_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = post_body

        view = views.ManageAccountPublishingViews(db_request)

        monkeypatch.setattr(
            views.PendingGitHubPublisherForm,
            "_lookup_owner",
            lambda *a: {"login": "some-owner", "id": "some-owner-id"},
        )
        monkeypatch.setattr(
            views.PendingActiveStatePublisherForm,
            "_lookup_organization",
            lambda *a: None,
        )
        monkeypatch.setattr(
            views.PendingActiveStatePublisherForm,
            "_lookup_actor",
            lambda *a: {"user_id": "some-user-id"},
        )

        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )

        assert getattr(view, view_name)() == view.default_response
        assert db_request.session.flash.calls == [
            pretend.call(
                (
                    "A pending trusted publisher matching this configuration "
                    "has already been registered for a different project name. "
                    "Please contact PyPI's admins if this wasn't intentional."
                ),
                queue="error",
            )
        ]
        # The conflicting INSERT left the transaction aborted. Without an
        # explicit rollback in the handler this query raises PendingRollbackError
        # -- which is what surfaces to the user as a 500/503 once the template
        # tries to render the user's existing pending publishers. The rollback
        # also discards this request's uncommitted work, including the
        # pre-existing publisher created above, so the count is 0.
        assert db_request.db.query(publisher_class).count() == 0

    @pytest.mark.parametrize(
        ("view_name", "publisher_name", "post_body", "publisher_class"),
        [
            (
                "add_pending_github_oidc_publisher",
                "GitHub",
                MultiDict(
                    {
                        "owner": "some-owner",
                        "repository": "some-repository",
                        "workflow_filename": "some-workflow-filename.yml",
                        "environment": "some-environment",
                        "project_name": "some-project-name",
                    }
                ),
                PendingGitHubPublisher,
            ),
            (
                "add_pending_gitlab_oidc_publisher",
                "GitLab",
                MultiDict(
                    {
                        "namespace": "some-owner",
                        "project": "some-repository",
                        "workflow_filepath": "subfolder/some-workflow-filename.yml",
                        "environment": "some-environment",
                        "project_name": "some-project-name",
                        "issuer_url": "https://gitlab.com",
                    }
                ),
                PendingGitLabPublisher,
            ),
            (
                "add_pending_google_oidc_publisher",
                "Google",
                MultiDict(
                    {
                        "email": "some-email@example.com",
                        "sub": "some-sub",
                        "project_name": "some-project-name",
                    }
                ),
                PendingGooglePublisher,
            ),
            (
                "add_pending_activestate_oidc_publisher",
                "ActiveState",
                MultiDict(
                    {
                        "organization": "some-org",
                        "project": "some-project",
                        "actor": "some-user",
                        "project_name": "some-project-name",
                    }
                ),
                PendingActiveStatePublisher,
            ),
        ],
    )
    def test_add_pending_oidc_publisher(
        self,
        monkeypatch,
        db_request,
        view_name,
        publisher_name,
        publisher_class,
        post_body,
    ):
        db_request.user = UserFactory()
        db_request.user.record_event = pretend.call_recorder(lambda **kw: None)
        EmailFactory(user=db_request.user, verified=True, primary=True)
        db_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = post_body
        monkeypatch.setattr(
            views.PendingGitHubPublisherForm,
            "_lookup_owner",
            lambda *a: {"login": "some-owner", "id": "some-owner-id"},
        )

        monkeypatch.setattr(
            views.PendingActiveStatePublisherForm,
            "_lookup_organization",
            lambda *a: None,
        )

        monkeypatch.setattr(
            views.PendingActiveStatePublisherForm,
            "_lookup_actor",
            lambda *a: {"user_id": "some-user-id"},
        )

        view = views.ManageAccountPublishingViews(db_request)

        monkeypatch.setattr(
            view, "_check_ratelimits", pretend.call_recorder(lambda: None)
        )
        monkeypatch.setattr(
            view, "_hit_ratelimits", pretend.call_recorder(lambda: None)
        )

        resp = getattr(view, view_name)()

        assert db_request.session.flash.calls == [
            pretend.call(
                "Registered a new pending publisher to create "
                "the project 'some-project-name'.",
                queue="success",
            )
        ]
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_pending_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
            pretend.call(
                "warehouse.oidc.add_pending_publisher.ok",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        assert view._hit_ratelimits.calls == [pretend.call()]
        assert view._check_ratelimits.calls == [pretend.call()]
        assert isinstance(resp, HTTPSeeOther)

        pending_publisher = db_request.db.query(publisher_class).one()
        assert pending_publisher.added_by_id == db_request.user.id

        mapping = {"owner": "repository_owner", "repository": "repository_name"}
        for k, v in post_body.items():
            assert getattr(pending_publisher, mapping.get(k, k)) == v

        assert db_request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.PendingOIDCPublisherAdded,
                request=db_request,
                additional={
                    "project": "some-project-name",
                    "publisher": pending_publisher.publisher_name,
                    "id": str(pending_publisher.id),
                    "specifier": str(pending_publisher),
                    "url": pending_publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                },
            )
        ]

    def test_delete_pending_oidc_publisher_admin_disabled(
        self, monkeypatch, pyramid_request
    ):
        project_service = pretend.stub(check_project_name=lambda name: None)
        pyramid_request.find_service = lambda interface, **kwargs: {
            IProjectService: project_service,
            IMetricsService: pretend.stub(),
        }[interface]

        pyramid_request.user = pretend.stub(id=pretend.stub())
        pyramid_request.db = pretend.stub(
            scalars=lambda *a, **kw: pretend.stub(all=lambda: [])
        )
        pyramid_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        pyramid_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: True)
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        pending_github_publisher_form_obj = pretend.stub()
        pending_github_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_github_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGitHubPublisherForm", pending_github_publisher_form_cls
        )
        pending_gitlab_publisher_form_obj = pretend.stub()
        pending_gitlab_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_gitlab_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGitLabPublisherForm", pending_gitlab_publisher_form_cls
        )
        pending_google_publisher_form_obj = pretend.stub()
        pending_google_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_google_publisher_form_obj
        )
        monkeypatch.setattr(
            views, "PendingGooglePublisherForm", pending_google_publisher_form_cls
        )
        pending_activestate_publisher_form_obj = pretend.stub()
        pending_activestate_publisher_form_cls = pretend.call_recorder(
            lambda *a, **kw: pending_activestate_publisher_form_obj
        )
        monkeypatch.setattr(
            views,
            "PendingActiveStatePublisherForm",
            pending_activestate_publisher_form_cls,
        )

        view = views.ManageAccountPublishingViews(pyramid_request)

        assert view.delete_pending_oidc_publisher() == {
            "disabled": {
                "GitHub": True,
                "GitLab": True,
                "Google": True,
                "ActiveState": True,
            },
            "project_names_with_publishers": [],
            "pending_github_publisher_form": pending_github_publisher_form_obj,
            "pending_gitlab_publisher_form": pending_gitlab_publisher_form_obj,
            "pending_google_publisher_form": pending_google_publisher_form_obj,
            "pending_activestate_publisher_form": pending_activestate_publisher_form_obj,  # noqa: E501
        }

        assert pyramid_request.flags.disallow_oidc.calls == [
            pretend.call(),
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                (
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
        ]
        assert pending_github_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                api_token="fake-api-token",
                route_url=pyramid_request.route_url,
                check_project_name=project_service.check_project_name,
                user=pyramid_request.user,
            )
        ]
        assert pending_gitlab_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                route_url=pyramid_request.route_url,
                check_project_name=project_service.check_project_name,
                user=pyramid_request.user,
            )
        ]

    def test_delete_pending_oidc_publisher_invalid_form(
        self, monkeypatch, pyramid_request
    ):
        pyramid_request.user = pretend.stub()
        pyramid_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.POST = MultiDict({"publisher_id": None})

        view = views.ManageAccountPublishingViews(pyramid_request)
        monkeypatch.setattr(
            views.ManageAccountPublishingViews, "default_response", pretend.stub()
        )

        assert view.delete_pending_oidc_publisher() == view.default_response
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_pending_publisher.attempt",
            ),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Invalid publisher ID",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("make_publisher", "publisher_class"),
        [
            (
                lambda user_id: PendingGitHubPublisher(
                    project_name="some-project-name",
                    repository_name="some-repository",
                    repository_owner="some-owner",
                    repository_owner_id="some-id",
                    workflow_filename="some-filename",
                    environment="",
                    added_by_id=user_id,
                ),
                PendingGitHubPublisher,
            ),
            (
                lambda user_id: PendingGitLabPublisher(
                    project_name="some-project-name",
                    namespace="some-owner",
                    project="some-repository",
                    workflow_filepath="subfolder/some-filename",
                    environment="",
                    issuer_url="https://gitlab.com",
                    added_by_id=user_id,
                ),
                PendingGitLabPublisher,
            ),
            (
                lambda user_id: PendingGooglePublisher(
                    project_name="some-project-name",
                    email="some-email@example.com",
                    sub="some-sub",
                    added_by_id=user_id,
                ),
                PendingGooglePublisher,
            ),
            (
                lambda user_id: PendingActiveStatePublisher(
                    project_name="some-project-name",
                    added_by_id=user_id,
                    organization="some-org",
                    activestate_project_name="some-project",
                    actor="some-user",
                    actor_id="some-user-id",
                ),
                PendingActiveStatePublisher,
            ),
        ],
    )
    def test_delete_pending_oidc_publisher_not_found(
        self, monkeypatch, db_request, make_publisher, publisher_class
    ):
        db_request.user = UserFactory.create()
        pending_publisher = make_publisher(db_request.user.id)
        db_request.db.add(pending_publisher)

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict({"publisher_id": str(uuid.uuid4())})

        view = views.ManageAccountPublishingViews(db_request)
        monkeypatch.setattr(
            views.ManageAccountPublishingViews, "default_response", pretend.stub()
        )

        assert view.delete_pending_oidc_publisher() == view.default_response
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_pending_publisher.attempt",
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Invalid publisher ID",
                queue="error",
            )
        ]
        assert db_request.db.query(publisher_class).all() == [pending_publisher]

    @pytest.mark.parametrize(
        ("make_publisher", "publisher_class"),
        [
            (
                lambda user_id: PendingGitHubPublisher(
                    project_name="some-project-name",
                    repository_name="some-repository",
                    repository_owner="some-owner",
                    repository_owner_id="some-id",
                    workflow_filename="some-filename",
                    environment="",
                    added_by_id=user_id,
                ),
                PendingGitHubPublisher,
            ),
            (
                lambda user_id: PendingGitLabPublisher(
                    project_name="some-project-name",
                    namespace="some-owner",
                    project="some-repository",
                    workflow_filepath="subfolder/some-filename",
                    environment="",
                    issuer_url="https://gitlab.com",
                    added_by_id=user_id,
                ),
                PendingGitLabPublisher,
            ),
            (
                lambda user_id: PendingGooglePublisher(
                    project_name="some-project-name",
                    email="some-email@example.com",
                    sub="some-sub",
                    added_by_id=user_id,
                ),
                PendingGooglePublisher,
            ),
        ],
    )
    def test_delete_pending_oidc_publisher_no_access(
        self, monkeypatch, db_request, make_publisher, publisher_class
    ):
        db_request.user = UserFactory.create()
        some_other_user = UserFactory.create()
        pending_publisher = make_publisher(some_other_user.id)
        db_request.db.add(pending_publisher)
        db_request.db.flush()  # To get the id

        db_request.user = pretend.stub()
        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = MultiDict({"publisher_id": str(pending_publisher.id)})

        view = views.ManageAccountPublishingViews(db_request)
        monkeypatch.setattr(
            views.ManageAccountPublishingViews, "default_response", pretend.stub()
        )

        assert view.delete_pending_oidc_publisher() == view.default_response
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_pending_publisher.attempt",
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Invalid publisher ID",
                queue="error",
            )
        ]
        assert db_request.db.query(publisher_class).all() == [pending_publisher]

    @pytest.mark.parametrize(
        ("publisher_name", "make_publisher", "publisher_class"),
        [
            (
                "GitHub",
                lambda user_id: PendingGitHubPublisher(
                    project_name="some-project-name",
                    repository_name="some-repository",
                    repository_owner="some-owner",
                    repository_owner_id="some-id",
                    workflow_filename="some-filename",
                    environment="",
                    added_by_id=user_id,
                ),
                PendingGitHubPublisher,
            ),
            (
                "GitLab",
                lambda user_id: PendingGitLabPublisher(
                    project_name="some-project-name",
                    namespace="some-owner",
                    project="some-owner",
                    workflow_filepath="subfolder/some-filename",
                    environment="",
                    issuer_url="https://gitlab.com",
                    added_by_id=user_id,
                ),
                PendingGitLabPublisher,
            ),
            (
                "Google",
                lambda user_id: PendingGooglePublisher(
                    project_name="some-project-name",
                    email="some-email@example.com",
                    sub="some-sub",
                    added_by_id=user_id,
                ),
                PendingGooglePublisher,
            ),
        ],
    )
    def test_delete_pending_oidc_publisher(
        self, monkeypatch, db_request, publisher_name, make_publisher, publisher_class
    ):
        db_request.user = UserFactory.create()
        pending_publisher = make_publisher(db_request.user.id)
        db_request.db.add(pending_publisher)
        db_request.db.flush()  # To get the id

        db_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False)
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.user.record_event = pretend.call_recorder(lambda **kw: None)
        db_request.POST = MultiDict({"publisher_id": str(pending_publisher.id)})

        view = views.ManageAccountPublishingViews(db_request)

        assert view.delete_pending_oidc_publisher().__class__ == HTTPSeeOther
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.delete_pending_publisher.attempt",
            ),
            pretend.call(
                "warehouse.oidc.delete_pending_publisher.ok",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "Removed trusted publisher for project 'some-project-name'",
                queue="success",
            )
        ]
        assert db_request.user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.PendingOIDCPublisherRemoved,
                request=db_request,
                additional={
                    "project": "some-project-name",
                    "publisher": publisher_name,
                    "id": str(pending_publisher.id),
                    "specifier": str(pending_publisher),
                    "url": pending_publisher.publisher_url(),
                    "submitted_by": db_request.user.username,
                },
            )
        ]
        assert db_request.db.query(publisher_class).all() == []


class TestConfirmLogin:
    def test_already_logged_in(self, pyramid_request):
        pyramid_request.user = UserFactory.create()
        pyramid_request.route_path = pretend.call_recorder(lambda route: f"/{route}")
        result = views.confirm_login(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/index"
        assert pyramid_request.route_path.calls == [pretend.call("index")]

    def test_no_token(self, pyramid_request):
        pyramid_request.user = None
        pyramid_request.params = {}
        result = views.confirm_login(pyramid_request)
        assert result == {"repeat_window_minutes": 15}

    @pytest.mark.parametrize(
        ("exception", "message"),
        [
            (TokenInvalid, "Invalid token: please try to login again"),
            (TokenExpired, "Expired token: please try to login again"),
            (TokenMissing, "Invalid token: no token supplied"),
        ],
    )
    def test_token_error(self, pyramid_request, exception, message):
        pyramid_request.user = None
        pyramid_request.params = {"token": "foo"}
        token_service = pretend.stub(loads=pretend.raiser(exception))
        user_service = pretend.stub()
        pyramid_request.find_service = lambda interface, name=None, **kwargs: {
            ITokenService: {"confirm_login": token_service},
            IUserService: {None: user_service},
        }[interface][name]
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        pyramid_request.route_path = pretend.call_recorder(lambda r: f"/{r}")

        result = views.confirm_login(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/accounts.login"
        assert pyramid_request.session.flash.calls == [
            pretend.call(message, queue="error")
        ]

    def test_invalid_action(self, pyramid_request):
        pyramid_request.user = None
        pyramid_request.params = {"token": "foo"}
        token_data = {"action": "wrong-action"}
        token_service = pretend.stub(loads=pretend.call_recorder(lambda t: token_data))
        user_service = pretend.stub()
        pyramid_request.find_service = lambda interface, name=None, **kwargs: {
            ITokenService: {"confirm_login": token_service},
            IUserService: {None: user_service},
        }[interface][name]
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        pyramid_request.route_path = pretend.call_recorder(lambda r: f"/{r}")

        result = views.confirm_login(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/accounts.login"
        assert pyramid_request.session.flash.calls == [
            pretend.call("Invalid token: not a login confirmation token", queue="error")
        ]

    def test_user_not_found(self, pyramid_request):
        pyramid_request.user = None
        pyramid_request.params = {"token": "foo"}
        token_data = {
            "action": "login-confirmation",
            "user.id": str(uuid.uuid4()),
        }
        token_service = pretend.stub(loads=pretend.call_recorder(lambda t: token_data))
        user_service = pretend.stub(get_user=pretend.call_recorder(lambda uid: None))

        pyramid_request.find_service = lambda interface, name=None, **kwargs: {
            ITokenService: {"confirm_login": token_service},
            IUserService: {None: user_service},
        }[interface][name]
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        pyramid_request.route_path = pretend.call_recorder(lambda r: f"/{r}")

        result = views.confirm_login(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/accounts.login"
        assert pyramid_request.session.flash.calls == [
            pretend.call("Invalid token: user not found", queue="error")
        ]

    def test_unique_login_not_found(self, db_request):
        user = UserFactory.create(last_login=datetime.datetime.now(datetime.UTC))
        db_request.user = None
        db_request.params = {"token": "foo"}
        token_data = {
            "action": "login-confirmation",
            "user.id": str(user.id),
            "user.last_login": user.last_login.isoformat(),
            "unique_login_id": str(uuid.uuid4()),
        }
        token_service = pretend.stub(loads=pretend.call_recorder(lambda t: token_data))
        user_service = pretend.stub(get_user=pretend.call_recorder(lambda uid: user))

        db_request.find_service = lambda interface, name=None, **kwargs: {
            ITokenService: {"confirm_login": token_service},
            IUserService: {None: user_service},
        }[interface][name]
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        db_request.route_path = pretend.call_recorder(lambda r: f"/{r}")

        result = views.confirm_login(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/accounts.login"
        assert db_request.session.flash.calls == [
            pretend.call("Invalid login attempt.", queue="error")
        ]

    def test_ip_address_mismatch(self, db_request):
        user = UserFactory.create(last_login=datetime.datetime.now(datetime.UTC))
        ip_address = IpAddressFactory.create(ip_address="1.1.1.1")
        unique_login = UserUniqueLoginFactory.create(user=user, ip_address=ip_address)
        db_request.user = None
        db_request.params = {"token": "foo"}
        token_data = {
            "action": "login-confirmation",
            "user.id": str(user.id),
            "user.last_login": user.last_login.isoformat(),
            "unique_login_id": unique_login.id,
        }
        token_service = pretend.stub(loads=pretend.call_recorder(lambda t: token_data))
        user_service = pretend.stub(get_user=pretend.call_recorder(lambda uid: user))

        db_request.find_service = lambda interface, name=None, **kwargs: {
            ITokenService: {"confirm_login": token_service},
            IUserService: {None: user_service},
        }[interface][name]
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)
        db_request.route_path = pretend.call_recorder(lambda r: f"/{r}")

        result = views.confirm_login(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/accounts.login"
        assert db_request.session.flash.calls == [
            pretend.call(
                "Device details didn't match, please try again from the device you "
                "originally used to log in.",
                queue="error",
            )
        ]

    def test_success(self, monkeypatch, db_request):
        user = UserFactory.create(last_login=datetime.datetime.now(datetime.UTC))
        unique_login = UserUniqueLoginFactory.create(
            user=user,
            ip_address=db_request.ip_address,
        )
        db_request.user = None
        db_request.params = {"token": "foo"}

        token_data = {
            "action": "login-confirmation",
            "user.id": str(user.id),
            "user.last_login": user.last_login.isoformat(),
            "unique_login_id": str(unique_login.id),
        }
        token_service = pretend.stub(loads=pretend.call_recorder(lambda t: token_data))
        user_service = pretend.stub(get_user=pretend.call_recorder(lambda uid: user))

        db_request.find_service = lambda interface, name=None, **kwargs: {
            ITokenService: {"confirm_login": token_service},
            IUserService: {None: user_service},
        }[interface][name]

        _login_user = pretend.call_recorder(
            lambda request, userid, two_factor_method=None: [("foo", "bar")]
        )
        monkeypatch.setattr(views, "_login_user", _login_user)
        _set_userid_insecure_cookie = pretend.call_recorder(lambda resp, userid: None)
        monkeypatch.setattr(
            views, "_set_userid_insecure_cookie", _set_userid_insecure_cookie
        )

        db_request.route_path = pretend.call_recorder(lambda r: f"/{r}")

        result = views.confirm_login(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.location == "/manage.projects"
        assert unique_login.status == UniqueLoginStatus.CONFIRMED
        assert _login_user.calls == [
            pretend.call(db_request, user.id, two_factor_method="email-confirmation")
        ]
        assert _set_userid_insecure_cookie.calls == [pretend.call(result, user.id)]
