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
import json
import uuid

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
from sqlalchemy.exc import NoResultFound
from webauthn.authentication.verify_authentication_response import (
    VerifiedAuthentication,
)
from webob.multidict import MultiDict

from warehouse.accounts import views
from warehouse.accounts.interfaces import (
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
from warehouse.packaging.models import Role, RoleInvitation
from warehouse.rate_limiting.interfaces import IRateLimiter

from ...common.db.accounts import EmailFactory, UserFactory
from ...common.db.ip_addresses import IpAddressFactory
from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationRoleFactory,
)
from ...common.db.packaging import ProjectFactory, RoleFactory, RoleInvitationFactory


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
    def test_user_redirects_username(self, db_request):
        user = UserFactory.create()

        if user.username.upper() != user.username:
            username = user.username.upper()
        else:
            username = user.username.lower()

        db_request.current_route_path = pretend.call_recorder(
            lambda username: "/user/the-redirect/"
        )
        db_request.matchdict = {"username": username}

        result = views.profile(user, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.current_route_path.calls == [
            pretend.call(username=user.username)
        ]

    def test_returns_user(self, db_request):
        user = UserFactory.create()
        assert views.profile(user, db_request) == {"user": user, "projects": []}


class TestAccountsSearch:
    def test_unauthenticated_raises_401(self):
        pyramid_request = pretend.stub(user=None)
        with pytest.raises(HTTPUnauthorized):
            views.accounts_search(pyramid_request)

    def test_no_query_string_raises_400(self):
        pyramid_request = pretend.stub(user=pretend.stub(), params=MultiDict({}))
        with pytest.raises(HTTPBadRequest):
            views.accounts_search(pyramid_request)

    def test_returns_users_with_prefix(self, db_session, user_service):
        foo = UserFactory.create(username="foo")
        bas = [
            UserFactory.create(username="bar"),
            UserFactory.create(username="baz"),
        ]

        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda svc, **kw: {
                IUserService: user_service,
                IRateLimiter: pretend.stub(
                    test=pretend.call_recorder(lambda ip_address: True),
                    hit=pretend.call_recorder(lambda ip_address: None),
                ),
            }[svc],
            ip_address=IpAddressFactory.build(),
        )

        request.params = MultiDict({"username": "f"})
        result = views.accounts_search(request)
        assert result == {"users": [foo]}

        request.params = MultiDict({"username": "ba"})
        result = views.accounts_search(request)
        assert result == {"users": bas}

        request.params = MultiDict({"username": "zzz"})
        with pytest.raises(HTTPNotFound):
            views.accounts_search(request)

    def test_when_rate_limited(self, db_session):
        search_limiter = pretend.stub(
            test=pretend.call_recorder(lambda ip_address: False),
        )
        request = pretend.stub(
            user=pretend.stub(),
            find_service=lambda svc, **kw: {
                IRateLimiter: search_limiter,
            }[svc],
            ip_address=IpAddressFactory.build(),
        )

        request.params = MultiDict({"username": "foo"})
        result = views.accounts_search(request)

        assert search_limiter.test.calls == [pretend.call(request.ip_address)]
        assert result == {"users": []}


class TestLogin:
    @pytest.mark.parametrize("next_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_form(self, pyramid_request, pyramid_services, next_url):
        user_service = pretend.stub()
        breach_service = pretend.stub()

        pyramid_services.register_service(user_service, IUserService, None)
        pyramid_services.register_service(
            breach_service, IPasswordBreachedService, None
        )

        form_obj = pretend.stub()
        form_class = pretend.call_recorder(lambda d, **kw: form_obj)

        if next_url is not None:
            pyramid_request.GET["next"] = next_url

        result = views.login(pyramid_request, _form_class=form_class)

        assert result == {
            "form": form_obj,
            "redirect": {"field": "next", "data": next_url},
        }
        assert form_class.calls == [
            pretend.call(
                pyramid_request.POST,
                request=pyramid_request,
                user_service=user_service,
                breach_service=breach_service,
                check_password_metrics_tags=["method:auth", "auth_method:login_form"],
            )
        ]

    @pytest.mark.parametrize("next_url", [None, "/foo/bar/", "/wat/"])
    def test_post_invalid_returns_form(
        self, pyramid_request, pyramid_services, metrics, next_url
    ):
        user_service = pretend.stub()
        breach_service = pretend.stub()

        pyramid_services.register_service(user_service, IUserService, None)
        pyramid_services.register_service(
            breach_service, IPasswordBreachedService, None
        )

        pyramid_request.method = "POST"
        if next_url is not None:
            pyramid_request.POST["next"] = next_url
        form_obj = pretend.stub(validate=pretend.call_recorder(lambda: False))
        form_class = pretend.call_recorder(lambda d, **kw: form_obj)

        result = views.login(pyramid_request, _form_class=form_class)
        assert metrics.increment.calls == []

        assert result == {
            "form": form_obj,
            "redirect": {"field": "next", "data": next_url},
        }
        assert form_class.calls == [
            pretend.call(
                pyramid_request.POST,
                request=pyramid_request,
                user_service=user_service,
                breach_service=breach_service,
                check_password_metrics_tags=["method:auth", "auth_method:login_form"],
            )
        ]
        assert form_obj.validate.calls == [pretend.call()]

    @pytest.mark.parametrize("with_user", [True, False])
    def test_post_validate_redirects(
        self, monkeypatch, pyramid_request, pyramid_services, metrics, with_user
    ):
        remember = pretend.call_recorder(lambda request, user_id: [("foo", "bar")])
        monkeypatch.setattr(views, "remember", remember)

        new_session = {}

        user_id = uuid.uuid4()
        user = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: user_id),
            update_user=pretend.call_recorder(lambda *a, **kw: None),
            get_user=pretend.call_recorder(lambda userid: user),
            has_two_factor=lambda userid: False,
            get_password_timestamp=lambda userid: 0,
        )
        breach_service = pretend.stub(check_password=lambda password, tags=None: False)

        pyramid_services.register_service(user_service, IUserService, None)
        pyramid_services.register_service(
            breach_service, IPasswordBreachedService, None
        )

        pyramid_request.method = "POST"
        pyramid_request.session = pretend.stub(
            items=lambda: [("a", "b"), ("foo", "bar")],
            update=new_session.update,
            invalidate=pretend.call_recorder(lambda: None),
            new_csrf_token=pretend.call_recorder(lambda: None),
        )

        pyramid_request._unauthenticated_userid = (
            str(uuid.uuid4()) if with_user else None
        )

        pyramid_request.registry.settings = {"sessions.secret": "dummy_secret"}
        pyramid_request.session.record_auth_timestamp = pretend.call_recorder(
            lambda *args: None
        )
        pyramid_request.session.record_password_timestamp = lambda timestamp: None

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data="theuser"),
            password=pretend.stub(data="password"),
        )
        form_class = pretend.call_recorder(lambda d, **kw: form_obj)

        pyramid_request.route_path = pretend.call_recorder(lambda a: "/the-redirect")

        now = datetime.datetime.now(datetime.UTC)

        with freezegun.freeze_time(now):
            result = views.login(pyramid_request, _form_class=form_class)

        assert metrics.increment.calls == []

        assert isinstance(result, HTTPSeeOther)
        assert pyramid_request.route_path.calls == [pretend.call("manage.projects")]
        assert result.headers["Location"] == "/the-redirect"
        assert result.headers["foo"] == "bar"

        assert form_class.calls == [
            pretend.call(
                pyramid_request.POST,
                request=pyramid_request,
                user_service=user_service,
                breach_service=breach_service,
                check_password_metrics_tags=["method:auth", "auth_method:login_form"],
            )
        ]
        assert form_obj.validate.calls == [pretend.call()]

        assert user_service.find_userid.calls == [pretend.call("theuser")]
        assert user_service.update_user.calls == [pretend.call(user_id, last_login=now)]
        assert user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.LoginSuccess,
                request=pyramid_request,
                additional={"two_factor_method": None, "two_factor_label": None},
            )
        ]

        if with_user:
            assert new_session == {}
        else:
            assert new_session == {"a": "b", "foo": "bar"}

        assert remember.calls == [pretend.call(pyramid_request, str(user_id))]
        assert pyramid_request.session.invalidate.calls == [pretend.call()]
        assert pyramid_request.session.new_csrf_token.calls == [pretend.call()]
        assert pyramid_request.session.record_auth_timestamp.calls == [pretend.call()]

    @pytest.mark.parametrize(
        # The set of all possible next URLs. Since this set is infinite, we
        # test only a finite set of reasonable URLs.
        ("expected_next_url, observed_next_url"),
        [("/security/", "/security/"), ("http://example.com", "/the-redirect")],
    )
    def test_post_validate_no_redirects(
        self, pyramid_request, pyramid_services, expected_next_url, observed_next_url
    ):
        user = pretend.stub(
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        user_service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: user),
            find_userid=pretend.call_recorder(lambda username: 1),
            update_user=lambda *a, **k: None,
            has_two_factor=lambda userid: False,
            get_password_timestamp=lambda userid: 0,
        )
        breach_service = pretend.stub(check_password=lambda password, tags=None: False)

        pyramid_services.register_service(user_service, IUserService, None)
        pyramid_services.register_service(
            breach_service, IPasswordBreachedService, None
        )

        pyramid_request.method = "POST"
        pyramid_request.POST["next"] = expected_next_url

        pyramid_request.session.record_auth_timestamp = pretend.call_recorder(
            lambda *args: None
        )
        pyramid_request.session.record_password_timestamp = lambda timestamp: None

        security_policy = pretend.stub(
            identity=lambda r: None,
            remember=lambda r, u, **kw: [],
            reset=pretend.call_recorder(lambda r: None),
        )
        pyramid_request.registry.queryUtility = lambda iface: security_policy

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data="theuser"),
            password=pretend.stub(data="password"),
        )
        form_class = pretend.call_recorder(lambda d, **kw: form_obj)
        pyramid_request.route_path = pretend.call_recorder(lambda a: "/the-redirect")

        result = views.login(pyramid_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == observed_next_url
        assert user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.LoginSuccess,
                request=pyramid_request,
                additional={"two_factor_method": None, "two_factor_label": None},
            )
        ]
        assert pyramid_request.session.record_auth_timestamp.calls == [pretend.call()]
        assert security_policy.reset.calls == [pretend.call(pyramid_request)]

    def test_redirect_authenticated_user(self):
        pyramid_request = pretend.stub(user=pretend.stub())
        pyramid_request.route_path = pretend.call_recorder(lambda a: "/the-redirect")
        result = views.login(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    @pytest.mark.parametrize("redirect_url", ["test_redirect_url", None])
    def test_two_factor_auth(
        self, monkeypatch, pyramid_request, redirect_url, token_service
    ):
        token_service.dumps = lambda d: "fake_token"

        monkeypatch.setattr(
            views, "_check_remember_device_token", lambda *a, **kw: False
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            update_user=lambda *a, **k: None,
            has_two_factor=lambda userid: True,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )

        breach_service = pretend.stub(check_password=lambda pw: False)

        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service,
            IUserService: user_service,
            IPasswordBreachedService: breach_service,
        }[interface]

        pyramid_request.method = "POST"
        if redirect_url:
            pyramid_request.POST["next"] = redirect_url

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data="theuser"),
        )
        form_class = pretend.call_recorder(lambda d, user_service, **kw: form_obj)
        pyramid_request.route_path = pretend.call_recorder(
            lambda a, **kw: "/account/two-factor"
        )
        pyramid_request.params = pretend.stub(
            get=pretend.call_recorder(lambda k: {"userid": 1}[k])
        )
        result = views.login(pyramid_request, _form_class=form_class)

        token_expected_data = {"userid": 1}
        if redirect_url:
            token_expected_data["redirect_to"] = redirect_url

        assert isinstance(result, HTTPSeeOther)
        assert result.headerlist == [
            ("Content-Type", "text/html; charset=UTF-8"),
            ("Content-Length", "0"),
            ("Location", "/account/two-factor"),
        ]


class TestTwoFactor:
    def test_get_two_factor_data_invalid_after_login(self, pyramid_request):
        sign_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=30)
        last_login_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            seconds=1
        )

        query_params = {"userid": 1}
        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda *args, **kwargs: (query_params, sign_time)
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(last_login=last_login_time)
            ),
            update_user=lambda *a, **k: None,
            has_totp=lambda uid: True,
            has_webauthn=lambda uid: False,
            has_recovery_codes=lambda uid: False,
        )

        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service,
            IUserService: user_service,
        }[interface]
        pyramid_request.query_string = pretend.stub()

        with pytest.raises(TokenInvalid):
            views._get_two_factor_data(pyramid_request)

    def test_two_factor_and_totp_validate_redirect_to_account_login(
        self,
        db_request,
        token_service,
        user_service,
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

        token = token_service.dumps(token_data)
        db_request.query_string = token
        db_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service,
            IUserService: user_service,
        }[interface]
        db_request.route_path = pretend.call_recorder(lambda name: "/account/login/")

        two_factor_and_totp_validate(db_request)
        # This view is redirected to only during a TokenException recovery
        # which is called in two instances:
        # 1. No userid in token
        # 2. The token has expired
        assert db_request.route_path.calls == [pretend.call("accounts.login")]

    @pytest.mark.parametrize("redirect_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_totp_form(self, pyramid_request, redirect_url):
        query_params = {"userid": 1}
        if redirect_url:
            query_params["redirect_to"] = redirect_url

        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda *args, **kwargs: (
                    query_params,
                    datetime.datetime.now(datetime.UTC),
                )
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(
                        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
                    )
                )
            ),
            update_user=lambda *a, **k: None,
            has_totp=lambda uid: True,
            has_webauthn=lambda uid: False,
            has_recovery_codes=lambda uid: False,
        )

        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service,
            IUserService: user_service,
        }[interface]
        pyramid_request.registry.settings = {"remember_device.days": 30}
        pyramid_request.query_string = pretend.stub()

        form_obj = pretend.stub()
        form_class = pretend.call_recorder(lambda d, user_service, **kw: form_obj)

        result = views.two_factor_and_totp_validate(
            pyramid_request, _form_class=form_class
        )

        assert token_service.loads.calls == [
            pretend.call(pyramid_request.query_string, return_timestamp=True)
        ]
        assert result == {"totp_form": form_obj, "remember_device_days": 30}
        assert form_class.calls == [
            pretend.call(
                pyramid_request.POST,
                request=pyramid_request,
                user_id=1,
                user_service=user_service,
                check_password_metrics_tags=["method:auth", "auth_method:login_form"],
            )
        ]

    @pytest.mark.parametrize("redirect_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_webauthn(self, pyramid_request, redirect_url):
        query_params = {"userid": 1}
        if redirect_url:
            query_params["redirect_to"] = redirect_url

        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda *args, **kwargs: (
                    query_params,
                    datetime.datetime.now(datetime.UTC),
                )
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(
                        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
                    )
                )
            ),
            update_user=lambda *a, **k: None,
            has_totp=lambda uid: False,
            has_webauthn=lambda uid: True,
            has_recovery_codes=lambda uid: False,
        )

        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service,
            IUserService: user_service,
        }[interface]
        pyramid_request.registry.settings = {"remember_device.days": 30}
        pyramid_request.query_string = pretend.stub()

        result = views.two_factor_and_totp_validate(
            pyramid_request, _form_class=pretend.stub()
        )

        assert token_service.loads.calls == [
            pretend.call(pyramid_request.query_string, return_timestamp=True)
        ]
        assert result == {"has_webauthn": True, "remember_device_days": 30}

    @pytest.mark.parametrize("redirect_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_recovery_code_status(self, pyramid_request, redirect_url):
        query_params = {"userid": 1}
        if redirect_url:
            query_params["redirect_to"] = redirect_url

        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda *args, **kwargs: (
                    query_params,
                    datetime.datetime.now(datetime.UTC),
                )
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(
                        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
                    )
                )
            ),
            update_user=lambda *a, **k: None,
            has_totp=lambda uid: False,
            has_webauthn=lambda uid: False,
            has_recovery_codes=lambda uid: True,
        )

        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service,
            IUserService: user_service,
        }[interface]
        pyramid_request.registry.settings = {"remember_device.days": 30}
        pyramid_request.query_string = pretend.stub()

        result = views.two_factor_and_totp_validate(
            pyramid_request, _form_class=pretend.stub()
        )

        assert token_service.loads.calls == [
            pretend.call(pyramid_request.query_string, return_timestamp=True)
        ]
        assert result == {"has_recovery_codes": True, "remember_device_days": 30}

    @pytest.mark.parametrize("redirect_url", ["test_redirect_url", None])
    @pytest.mark.parametrize("has_recovery_codes", [True, False])
    @pytest.mark.parametrize("remember_device", [True, False])
    def test_totp_auth(
        self,
        monkeypatch,
        pyramid_request,
        redirect_url,
        has_recovery_codes,
        remember_device,
    ):
        remember = pretend.call_recorder(lambda request, user_id: [("foo", "bar")])
        monkeypatch.setattr(views, "remember", remember)

        _remember_device = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "_remember_device", _remember_device)

        query_params = {"userid": str(1)}
        if redirect_url:
            query_params["redirect_to"] = redirect_url

        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda *args, **kwargs: (
                    query_params,
                    datetime.datetime.now(datetime.UTC),
                )
            )
        )

        user = pretend.stub(
            last_login=(
                datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
            ),
            has_recovery_codes=has_recovery_codes,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(lambda userid: user),
            update_user=lambda *a, **k: None,
            has_totp=lambda userid: True,
            has_webauthn=lambda userid: False,
            has_recovery_codes=lambda userid: has_recovery_codes,
            check_totp_value=lambda userid, totp_value: True,
            get_password_timestamp=lambda userid: 0,
        )

        new_session = {}

        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service,
            IUserService: user_service,
        }[interface]

        pyramid_request.method = "POST"
        pyramid_request.session = pretend.stub(
            items=lambda: [("a", "b"), ("foo", "bar")],
            update=new_session.update,
            invalidate=pretend.call_recorder(lambda: None),
            new_csrf_token=pretend.call_recorder(lambda: None),
            get_password_timestamp=lambda userid: 0,
        )

        pyramid_request.session.record_auth_timestamp = pretend.call_recorder(
            lambda *args: None
        )
        pyramid_request.session.record_password_timestamp = lambda timestamp: None
        pyramid_request.registry.settings = {"remember_device.days": 30}

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            totp_value=pretend.stub(data="test-otp-secret"),
            remember_device=pretend.stub(data=remember_device),
        )
        form_class = pretend.call_recorder(lambda d, user_service, **kw: form_obj)
        pyramid_request.route_path = pretend.call_recorder(
            lambda a: "/account/two-factor"
        )
        pyramid_request.params = pretend.stub(
            get=pretend.call_recorder(lambda k: query_params.get(k))
        )
        pyramid_request.user = user

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_recovery_code_reminder_email", send_email)

        result = views.two_factor_and_totp_validate(
            pyramid_request, _form_class=form_class
        )

        token_expected_data = {"userid": str(1)}
        if redirect_url:
            token_expected_data["redirect_to"] = redirect_url

        assert isinstance(result, HTTPSeeOther)

        assert remember.calls == [pretend.call(pyramid_request, str(1))]
        assert pyramid_request.session.invalidate.calls == [pretend.call()]
        assert pyramid_request.session.new_csrf_token.calls == [pretend.call()]
        assert user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.LoginSuccess,
                request=pyramid_request,
                additional={"two_factor_method": "totp", "two_factor_label": "totp"},
            )
        ]
        assert pyramid_request.session.record_auth_timestamp.calls == [pretend.call()]
        assert send_email.calls == (
            [] if has_recovery_codes else [pretend.call(pyramid_request, user)]
        )

        assert _remember_device.calls == (
            []
            if not remember_device
            else [pretend.call(pyramid_request, result, str(1), "totp")]
        )

    def test_totp_auth_already_authed(self):
        request = pretend.stub(
            identity=pretend.stub(),
            route_path=pretend.call_recorder(lambda p: "redirect_to"),
        )
        result = views.two_factor_and_totp_validate(request)

        assert request.route_path.calls == [pretend.call("manage.projects")]

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "redirect_to"

    def test_totp_form_invalid(self):
        token_data = {"userid": 1}
        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda *args, **kwargs: (
                    token_data,
                    datetime.datetime.now(datetime.UTC),
                )
            )
        )

        user_service = pretend.stub(
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(
                        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
                    )
                )
            ),
            has_totp=lambda userid: True,
            has_webauthn=lambda userid: False,
            has_recovery_codes=lambda userid: False,
            check_totp_value=lambda userid, totp_value: False,
        )

        request = pretend.stub(
            POST={},
            method="POST",
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            identity=None,
            route_path=pretend.call_recorder(lambda p: "redirect_to"),
            find_service=lambda interface, **kwargs: {
                ITokenService: token_service,
                IUserService: user_service,
            }[interface],
            query_string=pretend.stub(),
            registry=pretend.stub(settings={"remember_device.days": 30}),
        )

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
            totp_value=pretend.stub(data="test-otp-secret"),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        result = views.two_factor_and_totp_validate(request, _form_class=form_class)

        assert token_service.loads.calls == [
            pretend.call(request.query_string, return_timestamp=True)
        ]
        assert result == {"totp_form": form_obj, "remember_device_days": 30}

    def test_two_factor_token_missing_userid(self, pyramid_request):
        token_service = pretend.stub(
            loads=pretend.call_recorder(lambda *a, **kw: ({}, None))
        )

        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.route_path = pretend.call_recorder(lambda p: "redirect_to")
        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service
        }[interface]
        pyramid_request.query_string = pretend.stub()

        result = views.two_factor_and_totp_validate(pyramid_request)

        assert token_service.loads.calls == [
            pretend.call(pyramid_request.query_string, return_timestamp=True)
        ]
        assert pyramid_request.route_path.calls == [pretend.call("accounts.login")]
        assert pyramid_request.session.flash.calls == [
            pretend.call("Invalid or expired two factor login.", queue="error")
        ]

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "redirect_to"

    def test_two_factor_token_invalid(self, pyramid_request):
        token_service = pretend.stub(loads=pretend.raiser(TokenException))

        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service
        }[interface]
        pyramid_request.route_path = pretend.call_recorder(lambda p: "redirect_to")

        result = views.two_factor_and_totp_validate(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "redirect_to"
        assert pyramid_request.session.flash.calls == [
            pretend.call("Invalid or expired two factor login.", queue="error")
        ]


class TestWebAuthn:
    def test_webauthn_get_options_already_authenticated(self):
        request = pretend.stub(user=pretend.stub(), _=lambda a: a)

        result = views.webauthn_authentication_options(request)

        assert result == {"fail": {"errors": ["Already authenticated"]}}

    def test_webauthn_get_options_invalid_token(self, monkeypatch, pyramid_request):
        _get_two_factor_data = pretend.raiser(TokenException)
        monkeypatch.setattr(views, "_get_two_factor_data", _get_two_factor_data)

        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.webauthn_authentication_options(pyramid_request)

        assert pyramid_request.session.flash.calls == [
            pretend.call("Invalid or expired two factor login.", queue="error")
        ]
        assert result == {"fail": {"errors": ["Invalid or expired two factor login."]}}

    def test_webauthn_get_options(self, monkeypatch):
        _get_two_factor_data = pretend.call_recorder(
            lambda r: {"redirect_to": "foobar", "userid": 1}
        )
        monkeypatch.setattr(views, "_get_two_factor_data", _get_two_factor_data)

        user_service = pretend.stub(
            get_webauthn_assertion_options=lambda *a, **kw: {"not": "real"}
        )

        request = pretend.stub(
            session=pretend.stub(
                flash=pretend.call_recorder(lambda *a, **kw: None),
                get_webauthn_challenge=pretend.call_recorder(lambda: "not_real"),
            ),
            registry=pretend.stub(settings=pretend.stub(get=lambda *a: pretend.stub())),
            domain=pretend.stub(),
            user=None,
            find_service=lambda interface, **kwargs: user_service,
        )

        result = views.webauthn_authentication_options(request)

        assert _get_two_factor_data.calls == [pretend.call(request)]
        assert result == {"not": "real"}

    def test_webauthn_validate_already_authenticated(self):
        # TODO: Determine why we can't use `request.user` here.
        request = pretend.stub(identity=pretend.stub())
        result = views.webauthn_authentication_validate(request)

        assert result == {"fail": {"errors": ["Already authenticated"]}}

    def test_webauthn_validate_invalid_token(self, monkeypatch, pyramid_request):
        _get_two_factor_data = pretend.raiser(TokenException)
        monkeypatch.setattr(views, "_get_two_factor_data", _get_two_factor_data)

        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        result = views.webauthn_authentication_validate(pyramid_request)

        assert pyramid_request.session.flash.calls == [
            pretend.call("Invalid or expired two factor login.", queue="error")
        ]
        assert result == {"fail": {"errors": ["Invalid or expired two factor login."]}}

    def test_webauthn_validate_invalid_form(self, monkeypatch):
        _get_two_factor_data = pretend.call_recorder(
            lambda r: {"redirect_to": "foobar", "userid": 1}
        )
        monkeypatch.setattr(views, "_get_two_factor_data", _get_two_factor_data)

        request = pretend.stub(
            # TODO: Determine why we can't use `request.user` here.
            identity=None,
            POST={},
            session=pretend.stub(
                get_webauthn_challenge=pretend.call_recorder(lambda: "not_real"),
                clear_webauthn_challenge=pretend.call_recorder(lambda: pretend.stub()),
            ),
            find_service=lambda *a, **kw: pretend.stub(),
            host_url=pretend.stub(),
            registry=pretend.stub(settings=pretend.stub(get=lambda *a: pretend.stub())),
            rp_id=pretend.stub(),
            domain=pretend.stub(),
        )

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
            credential=pretend.stub(errors=["Fake validation failure"]),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)
        monkeypatch.setattr(views, "WebAuthnAuthenticationForm", form_class)

        result = views.webauthn_authentication_validate(request)

        assert _get_two_factor_data.calls == [pretend.call(request)]
        assert request.session.get_webauthn_challenge.calls == [pretend.call()]
        assert request.session.clear_webauthn_challenge.calls == [pretend.call()]

        assert result == {"fail": {"errors": ["Fake validation failure"]}}

    @pytest.mark.parametrize("has_recovery_codes", [True, False])
    @pytest.mark.parametrize("remember_device", [True, False])
    def test_webauthn_validate(
        self, monkeypatch, pyramid_request, has_recovery_codes, remember_device
    ):
        _get_two_factor_data = pretend.call_recorder(
            lambda r: {"redirect_to": "foobar", "userid": 1}
        )
        monkeypatch.setattr(views, "_get_two_factor_data", _get_two_factor_data)

        _login_user = pretend.call_recorder(lambda *a, **kw: pretend.stub())
        monkeypatch.setattr(views, "_login_user", _login_user)

        _remember_device = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "_remember_device", _remember_device)

        user = pretend.stub(
            webauthn=pretend.stub(sign_count=pretend.stub()),
            has_recovery_codes=has_recovery_codes,
        )

        user_service = pretend.stub(
            get_user=pretend.call_recorder(lambda uid: user),
            get_webauthn_by_credential_id=pretend.call_recorder(
                lambda *a: pretend.stub(label="webauthn_label")
            ),
        )
        pyramid_request.session = pretend.stub(
            get_webauthn_challenge=pretend.call_recorder(lambda: "not_real"),
            clear_webauthn_challenge=pretend.call_recorder(lambda: pretend.stub()),
        )
        pyramid_request.find_service = lambda *a, **kw: user_service
        pyramid_request.user = user

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            credential=pretend.stub(errors=["Fake validation failure"]),
            validated_credential=VerifiedAuthentication(
                credential_id=b"",
                new_sign_count=1,
                credential_device_type="single_device",
                credential_backed_up=False,
            ),
            remember_device=pretend.stub(data=remember_device),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)
        monkeypatch.setattr(views, "WebAuthnAuthenticationForm", form_class)

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_recovery_code_reminder_email", send_email)

        result = views.webauthn_authentication_validate(pyramid_request)

        assert _get_two_factor_data.calls == [pretend.call(pyramid_request)]
        assert _login_user.calls == [
            pretend.call(
                pyramid_request,
                1,
                "webauthn",
                two_factor_label="webauthn_label",
            )
        ]
        assert pyramid_request.session.get_webauthn_challenge.calls == [pretend.call()]
        assert pyramid_request.session.clear_webauthn_challenge.calls == [
            pretend.call()
        ]
        assert send_email.calls == (
            [] if has_recovery_codes else [pretend.call(pyramid_request, user)]
        )

        assert _remember_device.calls == (
            []
            if not remember_device
            else [
                pretend.call(pyramid_request, pyramid_request.response, 1, "webauthn")
            ]
        )

        assert result == {
            "success": "Successful WebAuthn assertion",
            "redirect_to": "foobar",
        }


class TestRememberDevice:
    def test_check_remember_device_token_valid(self):
        token_service = pretend.stub(loads=lambda *a: {"user_id": str(1)})
        request = pretend.stub(
            cookies=pretend.stub(get=lambda *a, **kw: "token"),
            find_service=lambda interface, **kwargs: {
                ITokenService: token_service,
            }[interface],
        )
        assert views._check_remember_device_token(request, 1)

    def test_check_remember_device_token_invalid_no_cookie(self):
        request = pretend.stub(
            cookies=pretend.stub(get=lambda *a, **kw: ""),
        )
        assert not views._check_remember_device_token(request, 1)

    def test_check_remember_device_token_invalid_bad_token(self):
        token_service = pretend.stub(loads=pretend.raiser(TokenException))
        request = pretend.stub(
            cookies=pretend.stub(get=lambda *a, **kw: "token"),
            find_service=lambda interface, **kwargs: {
                ITokenService: token_service,
            }[interface],
        )
        assert not views._check_remember_device_token(request, 1)

    def test_check_remember_device_token_invalid_wrong_user(self):
        token_service = pretend.stub(loads=lambda *a: {"user_id": str(999)})
        request = pretend.stub(
            cookies=pretend.stub(get=lambda *a, **kw: "token"),
            find_service=lambda interface, **kwargs: {
                ITokenService: token_service,
            }[interface],
        )
        assert not views._check_remember_device_token(request, 1)

    def test_remember_device(self):
        token_service = pretend.stub(dumps=lambda *a: "token_data")
        pyramid_request = pretend.stub(
            find_service=lambda interface, **kwargs: {
                ITokenService: token_service,
            }[interface],
            scheme="https",
            route_path=lambda *a, **kw: "/accounts/login",
            user=pretend.stub(
                record_event=pretend.call_recorder(lambda *a, **kw: None)
            ),
            registry=pretend.stub(
                settings={
                    "remember_device.seconds": datetime.timedelta(
                        days=30
                    ).total_seconds()
                }
            ),
        )
        response = pretend.stub(set_cookie=pretend.call_recorder(lambda *a, **kw: None))

        views._remember_device(pyramid_request, response, 1, "webauthn")

        assert response.set_cookie.calls == [
            pretend.call(
                REMEMBER_DEVICE_COOKIE,
                "token_data",
                max_age=datetime.timedelta(days=30).total_seconds(),
                httponly=True,
                secure=True,
                samesite=b"strict",
                path="/accounts/login",
            )
        ]


class TestRecoveryCode:
    def test_already_authenticated(self):
        request = pretend.stub(
            user=pretend.stub(),
            route_path=pretend.call_recorder(lambda p: "redirect_to"),
        )
        result = views.recovery_code(request)

        assert request.route_path.calls == [pretend.call("manage.projects")]

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "redirect_to"

    def test_two_factor_token_invalid(self, pyramid_request):
        token_service = pretend.stub(loads=pretend.raiser(TokenException))
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.route_path = pretend.call_recorder(lambda p: "redirect_to")
        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service
        }[interface]

        result = views.recovery_code(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert pyramid_request.route_path.calls == [pretend.call("accounts.login")]
        assert result.headers["Location"] == "redirect_to"
        assert pyramid_request.session.flash.calls == [
            pretend.call("Invalid or expired two factor login.", queue="error")
        ]

    def test_get_returns_form(self, pyramid_request):
        query_params = {"userid": 1}

        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda *args, **kwargs: (
                    query_params,
                    datetime.datetime.now(datetime.UTC),
                )
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(
                        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
                    )
                )
            ),
            update_user=lambda *a, **k: None,
            has_totp=lambda uid: True,
            has_webauthn=lambda uid: False,
            has_recovery_codes=lambda uid: False,
        )

        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service,
            IUserService: user_service,
        }[interface]
        pyramid_request.query_string = pretend.stub()

        form_obj = pretend.stub()
        form_class = pretend.call_recorder(lambda d, user_service, **kw: form_obj)

        result = views.recovery_code(pyramid_request, _form_class=form_class)

        assert token_service.loads.calls == [
            pretend.call(pyramid_request.query_string, return_timestamp=True)
        ]
        assert result == {"form": form_obj}
        assert form_class.calls == [
            pretend.call(
                pyramid_request.POST,
                request=pyramid_request,
                user_id=1,
                user_service=user_service,
            )
        ]

    @pytest.mark.parametrize("redirect_url", ["test_redirect_url", None])
    def test_recovery_code_auth(self, monkeypatch, pyramid_request, redirect_url):
        remember = pretend.call_recorder(lambda request, user_id: [("foo", "bar")])
        monkeypatch.setattr(views, "remember", remember)

        query_params = {"userid": str(1)}
        if redirect_url:
            query_params["redirect_to"] = redirect_url

        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda *args, **kwargs: (
                    query_params,
                    datetime.datetime.now(datetime.UTC),
                )
            )
        )

        user = pretend.stub(
            last_login=(
                datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
            ),
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(lambda userid: user),
            update_user=lambda *a, **k: None,
            has_recovery_codes=lambda userid: True,
            check_recovery_code=lambda userid, recovery_code_value: True,
            get_password_timestamp=lambda userid: 0,
        )

        new_session = {}

        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service,
            IUserService: user_service,
        }[interface]

        pyramid_request.method = "POST"
        pyramid_request.session = pretend.stub(
            items=lambda: [("a", "b"), ("foo", "bar")],
            update=new_session.update,
            invalidate=pretend.call_recorder(lambda: None),
            new_csrf_token=pretend.call_recorder(lambda: None),
            flash=pretend.call_recorder(lambda message, queue: None),
        )

        pyramid_request.set_property(
            lambda r: str(uuid.uuid4()), name="unauthenticated_userid"
        )
        pyramid_request.session.record_auth_timestamp = pretend.call_recorder(
            lambda *args: None
        )
        pyramid_request.session.record_password_timestamp = lambda timestamp: None

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            recovery_code_value=pretend.stub(data="recovery-code"),
        )
        form_class = pretend.call_recorder(lambda d, user_service, **kw: form_obj)
        pyramid_request.route_path = pretend.call_recorder(
            lambda a: "/account/two-factor"
        )
        pyramid_request.params = pretend.stub(
            get=pretend.call_recorder(lambda k: query_params.get(k))
        )
        result = views.recovery_code(pyramid_request, _form_class=form_class)

        token_expected_data = {"userid": str(1)}
        if redirect_url:
            token_expected_data["redirect_to"] = redirect_url

        assert isinstance(result, HTTPSeeOther)

        assert remember.calls == [pretend.call(pyramid_request, str(1))]
        assert pyramid_request.session.invalidate.calls == [pretend.call()]
        assert pyramid_request.session.new_csrf_token.calls == [pretend.call()]
        assert user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.LoginSuccess,
                request=pyramid_request,
                additional={
                    "two_factor_method": "recovery-code",
                    "two_factor_label": None,
                },
            ),
            pretend.call(
                tag=EventTag.Account.RecoveryCodesUsed,
                request=pyramid_request,
            ),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Recovery code accepted. The supplied code cannot be used again.",
                queue="success",
            )
        ]
        assert pyramid_request.session.record_auth_timestamp.calls == [pretend.call()]

    def test_recovery_code_form_invalid(self):
        token_data = {"userid": 1}
        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda *args, **kwargs: (
                    token_data,
                    datetime.datetime.now(datetime.UTC),
                )
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(
                        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
                    )
                )
            ),
            has_recovery_codes=lambda userid: True,
            check_recovery_code=lambda userid, recovery_code_value: False,
        )

        request = pretend.stub(
            POST={},
            method="POST",
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            user=None,
            route_path=pretend.call_recorder(lambda p: "redirect_to"),
            find_service=lambda interface, **kwargs: {
                ITokenService: token_service,
                IUserService: user_service,
            }[interface],
            query_string=pretend.stub(),
            # registry=pretend.stub(settings={"remember_device.days": 30}),
        )

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: False),
            recovery_code_value=pretend.stub(data="invalid-recovery-code"),
        )
        form_class = pretend.call_recorder(lambda *a, **kw: form_obj)

        result = views.recovery_code(request, _form_class=form_class)

        assert token_service.loads.calls == [
            pretend.call(request.query_string, return_timestamp=True)
        ]
        assert result == {"form": form_obj}

    def test_recovery_code_auth_invalid_token(self, pyramid_request):
        token_service = pretend.stub(loads=pretend.raiser(TokenException))
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        pyramid_request.route_path = pretend.call_recorder(lambda p: "redirect_to")
        pyramid_request.find_service = lambda interface, **kwargs: {
            ITokenService: token_service
        }[interface]

        result = views.recovery_code(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "redirect_to"
        assert pyramid_request.session.flash.calls == [
            pretend.call("Invalid or expired two factor login.", queue="error")
        ]


class TestLogout:
    @pytest.mark.parametrize("next_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_empty(self, pyramid_request, next_url):
        if next_url is not None:
            pyramid_request.GET["next"] = next_url

        pyramid_request.user = pretend.stub()

        assert views.logout(pyramid_request) == {
            "redirect": {"field": "next", "data": next_url or "/"}
        }

    def test_post_forgets_user(self, monkeypatch, pyramid_request):
        forget = pretend.call_recorder(lambda request: [("foo", "bar")])
        monkeypatch.setattr(views, "forget", forget)

        pyramid_request.user = pretend.stub()
        pyramid_request.method = "POST"
        pyramid_request.session = pretend.stub(
            invalidate=pretend.call_recorder(lambda: None)
        )

        security_policy = pretend.stub(
            reset=pretend.call_recorder(lambda r: None),
        )
        pyramid_request.registry.queryUtility = lambda iface: security_policy

        result = views.logout(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert result.headers["foo"] == "bar"
        assert forget.calls == [pretend.call(pyramid_request)]
        assert pyramid_request.session.invalidate.calls == [pretend.call()]
        assert security_policy.reset.calls == [pretend.call(pyramid_request)]

    @pytest.mark.parametrize(
        # The set of all possible next URLs. Since this set is infinite, we
        # test only a finite set of reasonable URLs.
        ("expected_next_url, observed_next_url"),
        [("/security/", "/security/"), ("http://example.com", "/")],
    )
    def test_post_redirects_user(
        self, pyramid_request, expected_next_url, observed_next_url
    ):
        pyramid_request.user = pretend.stub()
        pyramid_request.method = "POST"
        pyramid_request.POST["next"] = expected_next_url

        result = views.logout(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == observed_next_url

    @pytest.mark.parametrize(
        # The set of all possible next URLs. Since this set is infinite, we
        # test only a finite set of reasonable URLs.
        ("expected_next_url, observed_next_url"),
        [("/security/", "/security/"), ("http://example.com", "/")],
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
    def test_get(self, db_request):
        form_inst = pretend.stub()
        form = pretend.call_recorder(lambda *args, **kwargs: form_inst)
        db_request.find_service = pretend.call_recorder(
            lambda *args, **kwargs: pretend.stub(
                enabled=False, csp_policy=pretend.stub(), merge=lambda _: None
            )
        )
        result = views.register(db_request, _form_class=form)
        assert result["form"] is form_inst

    def test_redirect_authenticated_user(self):
        pyramid_request = pretend.stub(user=pretend.stub())
        pyramid_request.route_path = pretend.call_recorder(lambda a: "/the-redirect")
        result = views.register(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_register_honeypot(self, pyramid_request, monkeypatch):
        pyramid_request.method = "POST"
        create_user = pretend.call_recorder(lambda *args, **kwargs: None)
        add_email = pretend.call_recorder(lambda *args, **kwargs: None)
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.POST = {"confirm_form": "fuzzywuzzy@bears.com"}
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)

        result = views.register(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert create_user.calls == []
        assert add_email.calls == []
        assert send_email.calls == []

    def test_register_redirect(self, db_request, monkeypatch):
        db_request.method = "POST"

        record_event = pretend.call_recorder(lambda *a, **kw: None)
        user = pretend.stub(
            id=pretend.stub(),
            record_event=record_event,
        )
        email = pretend.stub()
        create_user = pretend.call_recorder(lambda *args, **kwargs: user)
        add_email = pretend.call_recorder(lambda *args, **kwargs: email)
        db_request.session.record_auth_timestamp = pretend.call_recorder(
            lambda *args: None
        )
        db_request.session.record_password_timestamp = lambda ts: None

        def _find_service(service=None, name=None, context=None):
            key = service or name
            return {
                IUserService: pretend.stub(
                    username_is_prohibited=lambda a: False,
                    find_userid=pretend.call_recorder(lambda _: None),
                    find_userid_by_email=pretend.call_recorder(lambda _: None),
                    update_user=lambda *args, **kwargs: None,
                    create_user=create_user,
                    get_user=lambda userid: user,
                    add_email=add_email,
                    check_password=lambda pw, tags=None: False,
                    get_password_timestamp=lambda uid: 0,
                ),
                IPasswordBreachedService: pretend.stub(
                    check_password=lambda pw, tags=None: False,
                ),
                IRateLimiter: pretend.stub(hit=lambda user_id: None),
                "csp": pretend.stub(merge=lambda *a, **kw: {}),
                ICaptchaService: pretend.stub(
                    csp_policy={}, enabled=True, verify_response=lambda a: True
                ),
            }[key]

        db_request.find_service = pretend.call_recorder(_find_service)
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.POST.update(
            {
                "username": "username_value",
                "new_password": "MyStr0ng!shP455w0rd",
                "password_confirm": "MyStr0ng!shP455w0rd",
                "email": "foo@bar.com",
                "full_name": "full_name",
                "g_recaptcha_response": "captchavalue",
            }
        )

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_email_verification_email", send_email)

        result = views.register(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert create_user.calls == [
            pretend.call("username_value", "full_name", "MyStr0ng!shP455w0rd")
        ]
        assert add_email.calls == [pretend.call(user.id, "foo@bar.com", primary=True)]
        assert send_email.calls == [pretend.call(db_request, (user, email))]
        assert record_event.calls == [
            pretend.call(
                tag=EventTag.Account.AccountCreate,
                request=db_request,
                additional={"email": "foo@bar.com"},
            ),
            pretend.call(
                tag=EventTag.Account.LoginSuccess,
                request=db_request,
                additional={"two_factor_method": None, "two_factor_label": None},
            ),
        ]

    def test_register_fails_with_admin_flag_set(self, db_request):
        # This flag was already set via migration, just need to enable it
        flag = db_request.db.get(
            AdminFlag, AdminFlagValue.DISALLOW_NEW_USER_REGISTRATION.value
        )
        flag.enabled = True

        db_request.method = "POST"

        db_request.POST.update(
            {
                "username": "username_value",
                "password": "MyStr0ng!shP455w0rd",
                "password_confirm": "MyStr0ng!shP455w0rd",
                "email": "foo@bar.com",
                "full_name": "full_name",
            }
        )

        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        db_request.route_path = pretend.call_recorder(lambda name: "/")

        result = views.register(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert db_request.session.flash.calls == [
            pretend.call(
                "New user registration temporarily disabled. "
                "See https://pypi.org/help#admin-intervention for details.",
                queue="error",
            )
        ]


class TestRequestPasswordReset:
    def test_get(self, pyramid_request, user_service):
        form_inst = pretend.stub()
        form_class = pretend.call_recorder(lambda *args, **kwargs: form_inst)
        pyramid_request.find_service = pretend.call_recorder(
            lambda *a, **kw: user_service
        )
        pyramid_request.POST = pretend.stub()
        result = views.request_password_reset(pyramid_request, _form_class=form_class)
        assert result["form"] is form_inst
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service)
        ]
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None)
        ]

    def test_request_password_reset(
        self, monkeypatch, pyramid_request, pyramid_config, user_service, token_service
    ):
        stub_user = pretend.stub(
            id=pretend.stub(),
            username=pretend.stub(),
            emails=[pretend.stub(email="foo@example.com")],
            can_reset_password=True,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOK")
        user_service.get_user_by_username = pretend.call_recorder(lambda a: stub_user)
        pyramid_request.find_service = pretend.call_recorder(
            lambda interface, **kw: {
                IUserService: user_service,
                ITokenService: token_service,
            }[interface]
        )
        form_obj = pretend.stub(
            username_or_email=pretend.stub(data=stub_user.username),
            validate=pretend.call_recorder(lambda: True),
        )
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)
        n_hours = token_service.max_age // 60 // 60
        send_password_reset_email = pretend.call_recorder(
            lambda *args, **kwargs: {"n_hours": n_hours}
        )
        monkeypatch.setattr(
            views, "send_password_reset_email", send_password_reset_email
        )

        result = views.request_password_reset(pyramid_request, _form_class=form_class)

        assert result == {"n_hours": n_hours}
        assert user_service.get_user_by_username.calls == [
            pretend.call(stub_user.username)
        ]
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name="password"),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service)
        ]
        assert send_password_reset_email.calls == [
            pretend.call(pyramid_request, (stub_user, None))
        ]
        assert stub_user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.PasswordResetRequest,
                request=pyramid_request,
            )
        ]

    def test_request_password_reset_with_email(
        self, monkeypatch, pyramid_request, pyramid_config, user_service, token_service
    ):
        stub_user = pretend.stub(
            id=uuid.uuid4(),
            email="foo@example.com",
            emails=[pretend.stub(email="foo@example.com")],
            can_reset_password=True,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOK")
        user_service.get_user_by_username = pretend.call_recorder(lambda a: None)
        user_service.get_user_by_email = pretend.call_recorder(lambda a: stub_user)
        user_service.ratelimiters = {
            "password.reset": pretend.stub(
                test=pretend.call_recorder(lambda *a, **kw: True),
                hit=pretend.call_recorder(lambda *a, **kw: None),
            )
        }
        pyramid_request.find_service = pretend.call_recorder(
            lambda interface, **kw: {
                IUserService: user_service,
                ITokenService: token_service,
            }[interface]
        )
        form_obj = pretend.stub(
            username_or_email=pretend.stub(data=stub_user.email),
            validate=pretend.call_recorder(lambda: True),
        )
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)
        n_hours = token_service.max_age // 60 // 60
        send_password_reset_email = pretend.call_recorder(
            lambda *args, **kwargs: {"n_hours": n_hours}
        )
        monkeypatch.setattr(
            views, "send_password_reset_email", send_password_reset_email
        )

        result = views.request_password_reset(pyramid_request, _form_class=form_class)

        assert result == {"n_hours": n_hours}
        assert user_service.get_user_by_username.calls == [
            pretend.call(stub_user.email)
        ]
        assert user_service.get_user_by_email.calls == [pretend.call(stub_user.email)]
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name="password"),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service)
        ]
        assert send_password_reset_email.calls == [
            pretend.call(pyramid_request, (stub_user, stub_user.emails[0]))
        ]
        assert stub_user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.PasswordResetRequest,
                request=pyramid_request,
            )
        ]
        assert user_service.ratelimiters["password.reset"].test.calls == [
            pretend.call(stub_user.id)
        ]
        assert user_service.ratelimiters["password.reset"].hit.calls == [
            pretend.call(stub_user.id)
        ]

    def test_request_password_reset_with_non_primary_email(
        self, monkeypatch, pyramid_request, pyramid_config, user_service, token_service
    ):
        stub_user = pretend.stub(
            id=uuid.uuid4(),
            email="foo@example.com",
            emails=[
                pretend.stub(email="foo@example.com"),
                pretend.stub(email="other@example.com"),
            ],
            can_reset_password=True,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOK")
        user_service.get_user_by_username = pretend.call_recorder(lambda a: None)
        user_service.get_user_by_email = pretend.call_recorder(lambda a: stub_user)
        user_service.ratelimiters = {
            "password.reset": pretend.stub(
                test=pretend.call_recorder(lambda *a, **kw: True),
                hit=pretend.call_recorder(lambda *a, **kw: None),
            )
        }
        pyramid_request.find_service = pretend.call_recorder(
            lambda interface, **kw: {
                IUserService: user_service,
                ITokenService: token_service,
            }[interface]
        )
        form_obj = pretend.stub(
            username_or_email=pretend.stub(data="other@example.com"),
            validate=pretend.call_recorder(lambda: True),
        )
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)
        n_hours = token_service.max_age // 60 // 60
        send_password_reset_email = pretend.call_recorder(
            lambda *args, **kwargs: {"n_hours": n_hours}
        )
        monkeypatch.setattr(
            views, "send_password_reset_email", send_password_reset_email
        )

        result = views.request_password_reset(pyramid_request, _form_class=form_class)

        assert result == {"n_hours": n_hours}
        assert user_service.get_user_by_username.calls == [
            pretend.call("other@example.com")
        ]
        assert user_service.get_user_by_email.calls == [
            pretend.call("other@example.com")
        ]
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name="password"),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service)
        ]
        assert send_password_reset_email.calls == [
            pretend.call(pyramid_request, (stub_user, stub_user.emails[1]))
        ]
        assert stub_user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.PasswordResetRequest,
                request=pyramid_request,
            )
        ]
        assert user_service.ratelimiters["password.reset"].test.calls == [
            pretend.call(stub_user.id)
        ]
        assert user_service.ratelimiters["password.reset"].hit.calls == [
            pretend.call(stub_user.id)
        ]

    def test_too_many_password_reset_requests(
        self,
        monkeypatch,
        pyramid_request,
        pyramid_config,
        user_service,
    ):
        stub_user = pretend.stub(
            id=uuid.uuid4(),
            email="foo@example.com",
            emails=[pretend.stub(email="foo@example.com")],
            can_reset_password=True,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        pyramid_request.method = "POST"
        user_service.get_user_by_username = pretend.call_recorder(lambda a: None)
        user_service.get_user_by_email = pretend.call_recorder(lambda a: stub_user)
        user_service.ratelimiters = {
            "password.reset": pretend.stub(
                test=pretend.call_recorder(lambda *a, **kw: False),
                resets_in=pretend.call_recorder(lambda *a, **kw: 600),
            )
        }
        pyramid_request.find_service = pretend.call_recorder(
            lambda interface, **kw: {
                IUserService: user_service,
            }[interface]
        )
        form_obj = pretend.stub(
            username_or_email=pretend.stub(data=stub_user.email),
            validate=pretend.call_recorder(lambda: True),
        )
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)

        with pytest.raises(TooManyPasswordResetRequests):
            views.request_password_reset(pyramid_request, _form_class=form_class)

        assert user_service.get_user_by_username.calls == [
            pretend.call(stub_user.email)
        ]
        assert user_service.get_user_by_email.calls == [pretend.call(stub_user.email)]
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service)
        ]
        assert user_service.ratelimiters["password.reset"].test.calls == [
            pretend.call(stub_user.id)
        ]
        assert user_service.ratelimiters["password.reset"].resets_in.calls == [
            pretend.call(stub_user.id)
        ]

    def test_password_reset_prohibited(
        self, monkeypatch, pyramid_request, pyramid_config, user_service
    ):
        stub_user = pretend.stub(
            id=pretend.stub(),
            username=pretend.stub(),
            emails=[pretend.stub(email="foo@example.com")],
            can_reset_password=False,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
        pyramid_request.method = "POST"
        pyramid_request.route_path = pretend.call_recorder(lambda a: "/the-redirect")
        user_service.get_user_by_username = pretend.call_recorder(lambda a: stub_user)
        pyramid_request.find_service = pretend.call_recorder(
            lambda interface, **kw: {
                IUserService: user_service,
            }[interface]
        )
        form_obj = pretend.stub(
            username_or_email=pretend.stub(data=stub_user.username),
            validate=pretend.call_recorder(lambda: True),
        )
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)

        result = views.request_password_reset(pyramid_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert pyramid_request.route_path.calls == [
            pretend.call("accounts.request-password-reset")
        ]
        assert result.headers["Location"] == "/the-redirect"

        assert stub_user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.PasswordResetAttempt,
                request=pyramid_request,
            )
        ]

    def test_password_reset_with_nonexistent_email(
        self, monkeypatch, pyramid_request, pyramid_config, user_service, token_service
    ):
        pyramid_request.method = "POST"
        pyramid_request.route_path = pretend.call_recorder(lambda a: "/the-redirect")
        user_service.get_user_by_username = pretend.call_recorder(lambda a: None)
        user_service.get_user_by_email = pretend.call_recorder(lambda a: None)
        pyramid_request.find_service = pretend.call_recorder(
            lambda interface, **kw: {
                IUserService: user_service,
                ITokenService: token_service,
            }[interface]
        )
        form_obj = pretend.stub(
            username_or_email=pretend.stub(data="foo@bar.net"),
            validate=pretend.call_recorder(lambda: True),
        )
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)

        result = views.request_password_reset(pyramid_request, _form_class=form_class)

        assert result == {"n_hours": 6}

    def test_redirect_authenticated_user(self):
        pyramid_request = pretend.stub(user=pretend.stub())
        pyramid_request.route_path = pretend.call_recorder(lambda a: "/the-redirect")
        result = views.request_password_reset(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestResetPassword:
    @pytest.mark.parametrize("dates_utc", (True, False))
    def test_get(self, db_request, user_service, token_service, dates_utc):
        user = UserFactory.create()
        form_inst = pretend.stub()
        form_class = pretend.call_recorder(lambda *args, **kwargs: form_inst)

        breach_service = pretend.stub(check_password=lambda pw: False)

        db_request.GET.update({"token": "RANDOM_KEY"})
        last_login = str(
            user.last_login if dates_utc else user.last_login.replace(tzinfo=None)
        )
        password_date = str(
            user.password_date if dates_utc else user.password_date.replace(tzinfo=None)
        )
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "password-reset",
                "user.id": str(user.id),
                "user.last_login": last_login,
                "user.password_date": password_date,
            }
        )
        db_request.find_service = pretend.call_recorder(
            lambda interface, **kwargs: {
                IUserService: user_service,
                ITokenService: token_service,
                IPasswordBreachedService: breach_service,
            }[interface]
        )

        result = views.reset_password(db_request, _form_class=form_class)

        assert result["form"] is form_inst
        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                username=user.username,
                full_name=user.name,
                email=user.email,
                user_service=user_service,
                breach_service=breach_service,
            )
        ]
        assert token_service.loads.calls == [pretend.call("RANDOM_KEY")]
        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(IPasswordBreachedService, context=None),
            pretend.call(ITokenService, name="password"),
        ]

    def test_reset_password(self, monkeypatch, db_request, user_service, token_service):
        user = UserFactory.create()
        db_request.method = "POST"
        db_request.POST.update({"token": "RANDOM_KEY"})
        form_obj = pretend.stub(
            new_password=pretend.stub(data="password_value"),
            validate=pretend.call_recorder(lambda *args: True),
        )

        form_class = pretend.call_recorder(lambda *args, **kwargs: form_obj)

        breach_service = pretend.stub(check_password=lambda pw: False)

        ratelimiter_service = pretend.stub(
            clear=pretend.call_recorder(lambda *a, **kw: None)
        )

        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_password_change_email", send_email)

        db_request.route_path = pretend.call_recorder(lambda name: "/account/login")
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "password-reset",
                "user.id": str(user.id),
                "user.last_login": str(user.last_login),
                "user.password_date": str(user.password_date),
            }
        )
        user_service.update_user = pretend.call_recorder(lambda *a, **kw: None)
        db_request.find_service = pretend.call_recorder(
            lambda interface, **kwargs: {
                IUserService: user_service,
                ITokenService: token_service,
                IPasswordBreachedService: breach_service,
                IRateLimiter: ratelimiter_service,
            }[interface]
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        now = datetime.datetime.now(datetime.UTC)

        with freezegun.freeze_time(now):
            result = views.reset_password(db_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/account/login"
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                username=user.username,
                full_name=user.name,
                email=user.email,
                user_service=user_service,
                breach_service=breach_service,
            )
        ]
        assert db_request.route_path.calls == [pretend.call("accounts.login")]
        assert token_service.loads.calls == [pretend.call("RANDOM_KEY")]
        assert user_service.update_user.calls == [
            pretend.call(user.id, password=form_obj.new_password.data)
        ]
        assert send_email.calls == [pretend.call(db_request, user)]
        assert db_request.session.flash.calls == [
            pretend.call("You have reset your password", queue="success")
        ]
        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(IPasswordBreachedService, context=None),
            pretend.call(ITokenService, name="password"),
            pretend.call(IRateLimiter, name="password.reset"),
        ]
        assert ratelimiter_service.clear.calls == [
            pretend.call(user.id),
        ]

    def test_reset_password_with_no_last_login_succeeds(
        self, monkeypatch, db_request, user_service, token_service
    ):
        user = UserFactory.create(last_login=None, password_date=None)
        # unclear why factory doesn't accept the None above
        user.last_login = user.password_date = None
        assert user.last_login is None
        assert user.password_date is None

        db_request.method = "POST"
        db_request.POST.update({"token": "RANDOM_KEY"})
        form_obj = pretend.stub(
            new_password=pretend.stub(data="password_value"),
            validate=pretend.call_recorder(lambda *args: True),
        )
        form_class = pretend.call_recorder(lambda *args, **kwargs: form_obj)
        breach_service = pretend.stub(check_password=lambda pw: False)
        ratelimiter_service = pretend.stub(
            clear=pretend.call_recorder(lambda *a, **kw: None)
        )
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, "send_password_change_email", send_email)
        db_request.route_path = pretend.call_recorder(lambda name: "/account/login")
        token_service.loads = pretend.call_recorder(
            lambda token: {
                "action": "password-reset",
                "user.id": str(user.id),
                "user.last_login": str(
                    datetime.datetime.min.replace(tzinfo=datetime.UTC)
                ),
                "user.password_date": str(
                    datetime.datetime.min.replace(tzinfo=datetime.UTC)
                ),
            }
        )
        user_service.update_user = pretend.call_recorder(lambda *a, **kw: None)
        db_request.find_service = pretend.call_recorder(
            lambda interface, **kwargs: {
                IUserService: user_service,
                ITokenService: token_service,
                IPasswordBreachedService: breach_service,
                IRateLimiter: ratelimiter_service,
            }[interface]
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.reset_password(db_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/account/login"
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                db_request.POST,
                username=user.username,
                full_name=user.name,
                email=user.email,
                user_service=user_service,
                breach_service=breach_service,
            )
        ]
        assert db_request.route_path.calls == [pretend.call("accounts.login")]
        assert token_service.loads.calls == [pretend.call("RANDOM_KEY")]
        assert user_service.update_user.calls == [
            pretend.call(user.id, password=form_obj.new_password.data)
        ]
        assert send_email.calls == [pretend.call(db_request, user)]
        assert db_request.session.flash.calls == [
            pretend.call("You have reset your password", queue="success")
        ]
        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(IPasswordBreachedService, context=None),
            pretend.call(ITokenService, name="password"),
            pretend.call(IRateLimiter, name="password.reset"),
        ]
        assert ratelimiter_service.clear.calls == [
            pretend.call(user.id),
        ]

    @pytest.mark.parametrize(
        ("exception", "message"),
        [
            (TokenInvalid, "Invalid token: request a new password reset link"),
            (TokenExpired, "Expired token: request a new password reset link"),
            (TokenMissing, "Invalid token: no token supplied"),
        ],
    )
    def test_reset_password_loads_failure(self, pyramid_request, exception, message):
        def loads(token):
            raise exception

        pyramid_request.find_service = lambda interface, **kwargs: {
            IUserService: pretend.stub(),
            ITokenService: pretend.stub(loads=loads),
            IPasswordBreachedService: pretend.stub(),
        }[interface]
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.reset_password(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call("accounts.request-password-reset")
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(message, queue="error")
        ]

    def test_reset_password_invalid_action(self, pyramid_request):
        data = {"action": "invalid-action"}
        token_service = pretend.stub(loads=pretend.call_recorder(lambda token: data))
        pyramid_request.find_service = lambda interface, **kwargs: {
            IUserService: pretend.stub(),
            ITokenService: token_service,
            IPasswordBreachedService: pretend.stub(),
        }[interface]
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.reset_password(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call("accounts.request-password-reset")
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call("Invalid token: not a password reset token", queue="error")
        ]

    def test_reset_password_invalid_user(self, pyramid_request):
        data = {
            "action": "password-reset",
            "user.id": "8ad1a4ac-e016-11e6-bf01-fe55135034f3",
        }
        token_service = pretend.stub(loads=pretend.call_recorder(lambda token: data))
        user_service = pretend.stub(get_user=pretend.call_recorder(lambda userid: None))
        pyramid_request.find_service = lambda interface, **kwargs: {
            IUserService: user_service,
            ITokenService: token_service,
            IPasswordBreachedService: pretend.stub(),
        }[interface]
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.reset_password(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call("accounts.request-password-reset")
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call("Invalid token: user not found", queue="error")
        ]
        assert user_service.get_user.calls == [pretend.call(uuid.UUID(data["user.id"]))]

    def test_reset_password_last_login_changed(self, pyramid_request):
        now = datetime.datetime.now(datetime.UTC)
        later = now + datetime.timedelta(hours=1)
        data = {
            "action": "password-reset",
            "user.id": "8ad1a4ac-e016-11e6-bf01-fe55135034f3",
            "user.last_login": str(now),
        }
        token_service = pretend.stub(loads=pretend.call_recorder(lambda token: data))
        user = pretend.stub(last_login=later, username="time-traveler")
        user_service = pretend.stub(get_user=pretend.call_recorder(lambda userid: user))
        pyramid_request.find_service = lambda interface, **kwargs: {
            IUserService: user_service,
            ITokenService: token_service,
            IPasswordBreachedService: pretend.stub(),
        }[interface]
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.reset_password(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call("accounts.request-password-reset")
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Invalid token: user has logged in since this token was requested",
                queue="error",
            )
        ]

    def test_reset_password_password_date_changed(self, pyramid_request):
        now = datetime.datetime.now(datetime.UTC)
        later = now + datetime.timedelta(hours=1)
        data = {
            "action": "password-reset",
            "user.id": "8ad1a4ac-e016-11e6-bf01-fe55135034f3",
            "user.last_login": str(now),
            "user.password_date": str(now),
        }
        token_service = pretend.stub(loads=pretend.call_recorder(lambda token: data))
        user = pretend.stub(last_login=now, password_date=later)
        user_service = pretend.stub(get_user=pretend.call_recorder(lambda userid: user))
        pyramid_request.find_service = lambda interface, **kwargs: {
            IUserService: user_service,
            ITokenService: token_service,
            IPasswordBreachedService: pretend.stub(),
        }[interface]
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.reset_password(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call("accounts.request-password-reset")
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Invalid token: password has already been changed since this "
                "token was requested",
                queue="error",
            )
        ]

    def test_redirect_authenticated_user(self):
        pyramid_request = pretend.stub(user=pretend.stub())
        pyramid_request.route_path = pretend.call_recorder(lambda a: "/the-redirect")
        result = views.reset_password(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestVerifyEmail:
    @pytest.mark.parametrize(
        ("is_primary", "confirm_message"),
        [
            (True, "This is your primary address."),
            (False, "You can now set this email as your primary address."),
        ],
    )
    def test_verify_email(
        self, db_request, user_service, token_service, is_primary, confirm_message
    ):
        user = UserFactory(is_active=False, totp_secret=None)
        email = EmailFactory(user=user, verified=False, primary=is_primary)
        db_request.user = user
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        token_service.loads = pretend.call_recorder(
            lambda token: {"action": "email-verify", "email.id": str(email.id)}
        )
        email_limiter = pretend.stub(clear=pretend.call_recorder(lambda a: None))
        verify_limiter = pretend.stub(clear=pretend.call_recorder(lambda a: None))
        services = {
            "email": token_service,
            "email.add": email_limiter,
            "email.verify": verify_limiter,
        }
        db_request.find_service = pretend.call_recorder(
            lambda a, name, **kwargs: services[name]
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        result = views.verify_email(db_request)

        db_request.db.flush()
        assert email.verified
        assert user.is_active
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert db_request.route_path.calls == [
            pretend.call("manage.account.two-factor")
        ]
        assert token_service.loads.calls == [pretend.call("RANDOM_KEY")]
        assert email_limiter.clear.calls == [pretend.call(db_request.remote_addr)]
        assert verify_limiter.clear.calls == [pretend.call(user.id)]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Email address {email.email} verified. " + confirm_message,
                queue="success",
            )
        ]
        assert db_request.find_service.calls == [
            pretend.call(ITokenService, name="email"),
            pretend.call(IRateLimiter, name="email.add"),
            pretend.call(IRateLimiter, name="email.verify"),
        ]

    @pytest.mark.parametrize(
        ("exception", "message"),
        [
            (TokenInvalid, "Invalid token: request a new email verification link"),
            (TokenExpired, "Expired token: request a new email verification link"),
            (TokenMissing, "Invalid token: no token supplied"),
        ],
    )
    def test_verify_email_loads_failure(self, pyramid_request, exception, message):
        def loads(token):
            raise exception

        pyramid_request.find_service = lambda *a, **kw: pretend.stub(loads=loads)
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.verify_email(pyramid_request)

        assert pyramid_request.route_path.calls == [pretend.call("manage.account")]
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

        views.verify_email(pyramid_request)

        assert pyramid_request.route_path.calls == [pretend.call("manage.account")]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Invalid token: not an email verification token", queue="error"
            )
        ]

    def test_verify_email_not_found(self, pyramid_request):
        data = {"action": "email-verify", "email.id": "invalid"}
        pyramid_request.find_service = lambda *a, **kw: pretend.stub(
            loads=lambda a: data
        )
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        def raise_no_result(*a):
            raise NoResultFound

        pyramid_request.db = pretend.stub(query=raise_no_result)

        views.verify_email(pyramid_request)

        assert pyramid_request.route_path.calls == [pretend.call("manage.account")]
        assert pyramid_request.session.flash.calls == [
            pretend.call("Email not found", queue="error")
        ]

    def test_verify_email_already_verified(self, db_request):
        user = UserFactory()
        email = EmailFactory(user=user, verified=True)
        data = {"action": "email-verify", "email.id": email.id}
        db_request.user = user
        db_request.find_service = lambda *a, **kw: pretend.stub(loads=lambda a: data)
        db_request.params = {"token": "RANDOM_KEY"}
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        views.verify_email(db_request)

        assert db_request.route_path.calls == [pretend.call("manage.account")]
        assert db_request.session.flash.calls == [
            pretend.call("Email already verified", queue="error")
        ]

    def test_verify_email_with_existing_2fa(self, db_request, token_service):
        user = UserFactory(is_active=False, totp_secret=b"secret")
        email = EmailFactory(user=user, verified=False, primary=False)
        db_request.user = user
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        token_service.loads = pretend.call_recorder(
            lambda token: {"action": "email-verify", "email.id": str(email.id)}
        )
        email_limiter = pretend.stub(clear=pretend.call_recorder(lambda a: None))
        verify_limiter = pretend.stub(clear=pretend.call_recorder(lambda a: None))
        services = {
            "email": token_service,
            "email.add": email_limiter,
            "email.verify": verify_limiter,
        }
        db_request.find_service = pretend.call_recorder(
            lambda a, name, **kwargs: services[name]
        )
        db_request.session.flash = pretend.call_recorder(lambda *a, **kw: None)

        assert db_request.user.has_two_factor

        result = views.verify_email(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert db_request.route_path.calls == [pretend.call("manage.account")]
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

    def test_verify_role_get_confirmation(self, db_request, token_service):
        desired_role = "Manager"
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        OrganizationInvitationFactory.create(
            organization=organization,
            user=user,
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
        RoleInvitationFactory.create(user=user, project=project)
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
        RoleInvitationFactory.create(user=user, project=project)

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

    def test_verify_role_get_confirmation(
        self, db_request, user_service, token_service
    ):
        project = ProjectFactory.create()
        user = UserFactory.create()
        RoleInvitationFactory.create(user=user, project=project)

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
                username=pyramid_request.user.username,
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


class TestManageAccountPublishingViews:
    def test_initializes(self, metrics):
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda *a, **kw: metrics),
            POST=MultiDict(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                }
            ),
        )
        view = views.ManageAccountPublishingViews(request)

        assert view.request is request
        assert view.metrics is metrics

        assert view.request.find_service.calls == [
            pretend.call(IMetricsService, context=None)
        ]

    @pytest.mark.parametrize(
        "ip_exceeded, user_exceeded",
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

            if name == "user_oidc.publisher.register":
                return user_rate_limiter
            else:
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
        )

        view = views.ManageAccountPublishingViews(request)

        assert view._ratelimiters == {
            "user.oidc": user_rate_limiter,
            "ip.oidc": ip_rate_limiter,
        }
        assert request.find_service.calls == [
            pretend.call(IMetricsService, context=None),
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
        request = pretend.stub(
            user=pretend.stub(),
            registry=pretend.stub(
                settings={
                    "github.token": "fake-api-token",
                }
            ),
            find_service=pretend.call_recorder(lambda *a, **kw: metrics),
            flags=pretend.stub(
                disallow_oidc=pretend.call_recorder(lambda f=None: False)
            ),
            POST=pretend.stub(),
        )

        project_factory = pretend.stub()
        project_factory_cls = pretend.call_recorder(lambda r: project_factory)
        monkeypatch.setattr(views, "ProjectFactory", project_factory_cls)

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
        assert project_factory_cls.calls == [pretend.call(request)]
        assert pending_github_publisher_form_cls.calls == [
            pretend.call(
                request.POST,
                api_token="fake-api-token",
                project_factory=project_factory,
            )
        ]
        assert pending_gitlab_publisher_form_cls.calls == [
            pretend.call(
                request.POST,
                project_factory=project_factory,
            )
        ]

    def test_manage_publishing_admin_disabled(self, monkeypatch, pyramid_request):
        pyramid_request.user = pretend.stub()
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

        project_factory = pretend.stub()
        project_factory_cls = pretend.call_recorder(lambda r: project_factory)
        monkeypatch.setattr(views, "ProjectFactory", project_factory_cls)

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
                project_factory=project_factory,
            )
        ]
        assert pending_gitlab_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                project_factory=project_factory,
            )
        ]

    @pytest.mark.parametrize(
        "view_name, flag, publisher_name",
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
        pyramid_request.user = pretend.stub()
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

        project_factory = pretend.stub()
        project_factory_cls = pretend.call_recorder(lambda r: project_factory)
        monkeypatch.setattr(views, "ProjectFactory", project_factory_cls)

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
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
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
                project_factory=project_factory,
            )
        ]
        assert pending_gitlab_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                project_factory=project_factory,
            )
        ]

    @pytest.mark.parametrize(
        "view_name, flag, publisher_name",
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
    ):
        pyramid_request.registry = pretend.stub(
            settings={
                "github.token": "fake-api-token",
            }
        )
        pyramid_request.user = pretend.stub(
            has_primary_verified_email=False,
        )
        pyramid_request.flags = pretend.stub(
            disallow_oidc=pretend.call_recorder(lambda f=None: False),
        )
        pyramid_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        project_factory = pretend.stub()
        project_factory_cls = pretend.call_recorder(lambda r: project_factory)
        monkeypatch.setattr(views, "ProjectFactory", project_factory_cls)

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
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
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
                project_factory=project_factory,
            )
        ]
        assert pending_gitlab_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                project_factory=project_factory,
            )
        ]

    @pytest.mark.parametrize(
        "view_name, flag, publisher_name, make_publisher, publisher_class",
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
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITHUB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GITLAB_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_GOOGLE_OIDC),
            pretend.call(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC),
        ]
        assert view.metrics.increment.calls == [
            pretend.call(
                "warehouse.oidc.add_pending_publisher.attempt",
                tags=[f"publisher:{publisher_name}"],
            ),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                (
                    "You can't register more than 3 pending trusted "
                    "publishers at once."
                ),
                queue="error",
            )
        ]
        assert len(db_request.db.query(publisher_class).all()) == 3

    @pytest.mark.parametrize(
        "view_name, publisher_name",
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
        "view_name, publisher_name",
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
        "view_name, publisher_name, make_publisher, post_body",
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
                    added_by_id=user_id,
                ),
                MultiDict(
                    {
                        "namespace": "some-owner",
                        "project": "some-repository",
                        "workflow_filepath": "subfolder/some-workflow-filename.yml",
                        "environment": "some-environment",
                        "project_name": "some-project-name",
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
                        "project_name": "some-other-project-name",
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
        "view_name, publisher_name, post_body, publisher_class",
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
        pyramid_request.user = pretend.stub()
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

        project_factory = pretend.stub()
        project_factory_cls = pretend.call_recorder(lambda r: project_factory)
        monkeypatch.setattr(views, "ProjectFactory", project_factory_cls)

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
                project_factory=project_factory,
            )
        ]
        assert pending_gitlab_publisher_form_cls.calls == [
            pretend.call(
                pyramid_request.POST,
                project_factory=project_factory,
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
        "make_publisher, publisher_class",
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
        "make_publisher, publisher_class",
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
        "publisher_name, make_publisher, publisher_class",
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
