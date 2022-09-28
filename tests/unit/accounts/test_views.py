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
import pytz

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPSeeOther
from sqlalchemy.orm.exc import NoResultFound
from webauthn.authentication.verify_authentication_response import (
    VerifiedAuthentication,
)

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
from warehouse.accounts.models import User
from warehouse.accounts.views import two_factor_and_totp_validate
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.organizations.models import (
    OrganizationInvitation,
    OrganizationRole,
    OrganizationRoleType,
)
from warehouse.packaging.models import Role, RoleInvitation
from warehouse.rate_limiting.interfaces import IRateLimiter

from ...common.db.accounts import EmailFactory, UserFactory
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
            "There have been too many unsuccessful login attempts. Try again later."
        )
        assert dict(resp.headers).get("Retry-After") == "600"

    def test_too_many_emails_added(self, pyramid_request):
        exc = TooManyEmailsAdded(resets_in=datetime.timedelta(seconds=600))

        resp = views.unverified_emails(exc, pyramid_request)

        assert resp.status == "429 Too Many Requests"
        assert resp.detail == (
            "Too many emails have been added to this account without verifying "
            "them. Check your inbox and follow the verification links. (IP: "
            f"{ pyramid_request.remote_addr })"
        )
        assert dict(resp.headers).get("Retry-After") == "600"

    def test_too_many_password_reset_requests(self, pyramid_request):
        exc = TooManyPasswordResetRequests(resets_in=datetime.timedelta(seconds=600))

        resp = views.incomplete_password_resets(exc, pyramid_request)

        assert resp.status == "429 Too Many Requests"
        assert resp.detail == (
            "Too many password resets have been requested for this account without "
            "completing them. Check your inbox and follow the verification links. (IP: "
            f"{ pyramid_request.remote_addr })"
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
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: user_id),
            update_user=pretend.call_recorder(lambda *a, **kw: None),
            has_two_factor=lambda userid: False,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
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

        pyramid_request.set_property(
            lambda r: str(uuid.uuid4()) if with_user else None,
            name="unauthenticated_userid",
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

        now = datetime.datetime.utcnow()

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
        assert user_service.record_event.calls == [
            pretend.call(
                user_id,
                tag="account:login:success",
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
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            update_user=lambda *a, **k: None,
            has_two_factor=lambda userid: False,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
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
        assert user_service.record_event.calls == [
            pretend.call(
                1,
                tag="account:login:success",
                additional={"two_factor_method": None, "two_factor_label": None},
            )
        ]
        assert pyramid_request.session.record_auth_timestamp.calls == [pretend.call()]

    def test_redirect_authenticated_user(self):
        pyramid_request = pretend.stub(authenticated_userid=1)
        pyramid_request.route_path = pretend.call_recorder(lambda a: "/the-redirect")
        result = views.login(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    @pytest.mark.parametrize("redirect_url", ["test_redirect_url", None])
    def test_two_factor_auth(self, pyramid_request, redirect_url, token_service):
        token_service.dumps = lambda d: "fake_token"

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
        assert user_service.record_event.calls == []


class TestTwoFactor:
    def test_get_two_factor_data_invalid_after_login(self, pyramid_request):
        sign_time = datetime.datetime.utcnow() - datetime.timedelta(seconds=30)
        last_login_time = datetime.datetime.utcnow() - datetime.timedelta(seconds=1)

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
        user = User(
            username="jdoe",
            name="Joe",
            password="any",
            is_active=True,
            last_login=datetime.datetime.utcnow() + datetime.timedelta(days=+1),
        )
        db_request.db.add(user)
        db_request.db.commit()
        # Make sure object is not in session,
        # so sqlalchemy loads it fresh from database and type works it's magic
        db_request.db.expunge(user)

        token_data = {"userid": user.id}
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
                lambda *args, **kwargs: (query_params, datetime.datetime.utcnow())
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(datetime.datetime.utcnow() - datetime.timedelta(days=1))
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

        result = views.two_factor_and_totp_validate(
            pyramid_request, _form_class=form_class
        )

        assert token_service.loads.calls == [
            pretend.call(pyramid_request.query_string, return_timestamp=True)
        ]
        assert result == {"totp_form": form_obj}
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
                lambda *args, **kwargs: (query_params, datetime.datetime.utcnow())
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(datetime.datetime.utcnow() - datetime.timedelta(days=1))
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

        pyramid_request.query_string = pretend.stub()
        result = views.two_factor_and_totp_validate(
            pyramid_request, _form_class=pretend.stub()
        )

        assert token_service.loads.calls == [
            pretend.call(pyramid_request.query_string, return_timestamp=True)
        ]
        assert result == {"has_webauthn": True}

    @pytest.mark.parametrize("redirect_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_recovery_code_status(self, pyramid_request, redirect_url):
        query_params = {"userid": 1}
        if redirect_url:
            query_params["redirect_to"] = redirect_url

        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda *args, **kwargs: (query_params, datetime.datetime.utcnow())
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(datetime.datetime.utcnow() - datetime.timedelta(days=1))
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

        pyramid_request.query_string = pretend.stub()
        result = views.two_factor_and_totp_validate(
            pyramid_request, _form_class=pretend.stub()
        )

        assert token_service.loads.calls == [
            pretend.call(pyramid_request.query_string, return_timestamp=True)
        ]
        assert result == {"has_recovery_codes": True}

    @pytest.mark.parametrize("redirect_url", ["test_redirect_url", None])
    @pytest.mark.parametrize("has_recovery_codes", [True, False])
    def test_totp_auth(
        self, monkeypatch, pyramid_request, redirect_url, has_recovery_codes
    ):
        remember = pretend.call_recorder(lambda request, user_id: [("foo", "bar")])
        monkeypatch.setattr(views, "remember", remember)

        query_params = {"userid": str(1)}
        if redirect_url:
            query_params["redirect_to"] = redirect_url

        token_service = pretend.stub(
            loads=pretend.call_recorder(
                lambda *args, **kwargs: (query_params, datetime.datetime.utcnow())
            )
        )

        user = pretend.stub(
            last_login=(datetime.datetime.utcnow() - datetime.timedelta(days=1)),
            has_recovery_codes=has_recovery_codes,
        )
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(lambda userid: user),
            update_user=lambda *a, **k: None,
            has_totp=lambda userid: True,
            has_webauthn=lambda userid: False,
            has_recovery_codes=lambda userid: has_recovery_codes,
            check_totp_value=lambda userid, totp_value: True,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
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

        pyramid_request.set_property(
            lambda r: str(uuid.uuid4()), name="unauthenticated_userid"
        )
        pyramid_request.session.record_auth_timestamp = pretend.call_recorder(
            lambda *args: None
        )
        pyramid_request.session.record_password_timestamp = lambda timestamp: None

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            totp_value=pretend.stub(data="test-otp-secret"),
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
        assert user_service.record_event.calls == [
            pretend.call(
                "1",
                tag="account:login:success",
                additional={"two_factor_method": "totp", "two_factor_label": "totp"},
            )
        ]
        assert pyramid_request.session.record_auth_timestamp.calls == [pretend.call()]
        assert send_email.calls == (
            [] if has_recovery_codes else [pretend.call(pyramid_request, user)]
        )

    def test_totp_auth_already_authed(self):
        request = pretend.stub(
            authenticated_userid="not_none",
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
                lambda *args, **kwargs: (token_data, datetime.datetime.utcnow())
            )
        )

        user_service = pretend.stub(
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(datetime.datetime.utcnow() - datetime.timedelta(days=1))
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
            authenticated_userid=None,
            route_path=pretend.call_recorder(lambda p: "redirect_to"),
            find_service=lambda interface, **kwargs: {
                ITokenService: token_service,
                IUserService: user_service,
            }[interface],
            query_string=pretend.stub(),
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
        assert result == {"totp_form": form_obj}

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
    def test_webauthn_get_options_already_authenticated(self, pyramid_request):
        request = pretend.stub(authenticated_userid=pretend.stub(), _=lambda a: a)

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
            authenticated_userid=None,
            find_service=lambda interface, **kwargs: user_service,
        )

        result = views.webauthn_authentication_options(request)

        assert _get_two_factor_data.calls == [pretend.call(request)]
        assert result == {"not": "real"}

    def test_webauthn_validate_already_authenticated(self):
        request = pretend.stub(authenticated_userid=pretend.stub())
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
            authenticated_userid=None,
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
    def test_webauthn_validate(self, monkeypatch, pyramid_request, has_recovery_codes):
        _get_two_factor_data = pretend.call_recorder(
            lambda r: {"redirect_to": "foobar", "userid": 1}
        )
        monkeypatch.setattr(views, "_get_two_factor_data", _get_two_factor_data)

        _login_user = pretend.call_recorder(lambda *a, **kw: pretend.stub())
        monkeypatch.setattr(views, "_login_user", _login_user)

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
                two_factor_method="webauthn",
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

        assert result == {
            "success": "Successful WebAuthn assertion",
            "redirect_to": "foobar",
        }


class TestRecoveryCode:
    def test_already_authenticated(self):
        request = pretend.stub(
            authenticated_userid="not_none",
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
                lambda *args, **kwargs: (query_params, datetime.datetime.utcnow())
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(datetime.datetime.utcnow() - datetime.timedelta(days=1))
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
                lambda *args, **kwargs: (query_params, datetime.datetime.utcnow())
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(datetime.datetime.utcnow() - datetime.timedelta(days=1))
                )
            ),
            update_user=lambda *a, **k: None,
            has_recovery_codes=lambda userid: True,
            check_recovery_code=lambda userid, recovery_code_value: True,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
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
        assert user_service.record_event.calls == [
            pretend.call(
                "1",
                tag="account:login:success",
                additional={
                    "two_factor_method": "recovery-code",
                    "two_factor_label": None,
                },
            ),
            pretend.call(
                "1",
                tag="account:recovery_codes:used",
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
                lambda *args, **kwargs: (token_data, datetime.datetime.utcnow())
            )
        )

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            get_user=pretend.call_recorder(
                lambda userid: pretend.stub(
                    last_login=(datetime.datetime.utcnow() - datetime.timedelta(days=1))
                )
            ),
            has_recovery_codes=lambda userid: True,
            check_recovery_code=lambda userid, recovery_code_value: False,
        )

        request = pretend.stub(
            POST={},
            method="POST",
            session=pretend.stub(flash=pretend.call_recorder(lambda *a, **kw: None)),
            authenticated_userid=None,
            route_path=pretend.call_recorder(lambda p: "redirect_to"),
            find_service=lambda interface, **kwargs: {
                ITokenService: token_service,
                IUserService: user_service,
            }[interface],
            query_string=pretend.stub(),
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

        result = views.logout(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert result.headers["foo"] == "bar"
        assert forget.calls == [pretend.call(pyramid_request)]
        assert pyramid_request.session.invalidate.calls == [pretend.call()]

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
        pyramid_request = pretend.stub(authenticated_userid=1)
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

        user = pretend.stub(id=pretend.stub())
        email = pretend.stub()
        create_user = pretend.call_recorder(lambda *args, **kwargs: user)
        add_email = pretend.call_recorder(lambda *args, **kwargs: email)
        record_event = pretend.call_recorder(lambda *a, **kw: None)
        db_request.session.record_auth_timestamp = pretend.call_recorder(
            lambda *args: None
        )
        db_request.session.record_password_timestamp = lambda ts: None
        db_request.find_service = pretend.call_recorder(
            lambda svc, name=None, context=None: {
                IUserService: pretend.stub(
                    username_is_prohibited=lambda a: False,
                    find_userid=pretend.call_recorder(lambda _: None),
                    find_userid_by_email=pretend.call_recorder(lambda _: None),
                    update_user=lambda *args, **kwargs: None,
                    create_user=create_user,
                    add_email=add_email,
                    check_password=lambda pw, tags=None: False,
                    record_event=record_event,
                    get_password_timestamp=lambda uid: 0,
                ),
                IPasswordBreachedService: pretend.stub(
                    check_password=lambda pw, tags=None: False,
                ),
                IRateLimiter: pretend.stub(hit=lambda user_id: None),
            }.get(svc)
        )
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.POST.update(
            {
                "username": "username_value",
                "new_password": "MyStr0ng!shP455w0rd",
                "password_confirm": "MyStr0ng!shP455w0rd",
                "email": "foo@bar.com",
                "full_name": "full_name",
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
                user.id,
                tag="account:create",
                additional={"email": "foo@bar.com"},
            ),
            pretend.call(
                user.id,
                tag="account:login:success",
                additional={"two_factor_method": None, "two_factor_label": None},
            ),
        ]

    def test_register_fails_with_admin_flag_set(self, db_request):
        # This flag was already set via migration, just need to enable it
        flag = db_request.db.query(AdminFlag).get(
            AdminFlagValue.DISALLOW_NEW_USER_REGISTRATION.value
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
            id=pretend.stub(), username=pretend.stub(), can_reset_password=True
        )
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOK")
        user_service.get_user_by_username = pretend.call_recorder(lambda a: stub_user)
        user_service.record_event = pretend.call_recorder(lambda *a, **kw: None)
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
        assert user_service.record_event.calls == [
            pretend.call(
                stub_user.id,
                tag="account:password:reset:request",
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
        )
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOK")
        user_service.get_user_by_username = pretend.call_recorder(lambda a: None)
        user_service.get_user_by_email = pretend.call_recorder(lambda a: stub_user)
        user_service.record_event = pretend.call_recorder(lambda *a, **kw: None)
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
        assert user_service.record_event.calls == [
            pretend.call(
                stub_user.id,
                tag="account:password:reset:request",
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
        )
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOK")
        user_service.get_user_by_username = pretend.call_recorder(lambda a: None)
        user_service.get_user_by_email = pretend.call_recorder(lambda a: stub_user)
        user_service.record_event = pretend.call_recorder(lambda *a, **kw: None)
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
        assert user_service.record_event.calls == [
            pretend.call(
                stub_user.id,
                tag="account:password:reset:request",
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
        )
        pyramid_request.method = "POST"
        user_service.get_user_by_username = pretend.call_recorder(lambda a: None)
        user_service.get_user_by_email = pretend.call_recorder(lambda a: stub_user)
        user_service.record_event = pretend.call_recorder(lambda *a, **kw: None)
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
            id=pretend.stub(), username=pretend.stub(), can_reset_password=False
        )
        pyramid_request.method = "POST"
        pyramid_request.route_path = pretend.call_recorder(lambda a: "/the-redirect")
        user_service.get_user_by_username = pretend.call_recorder(lambda a: stub_user)
        user_service.record_event = pretend.call_recorder(lambda *a, **kw: None)
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

        assert user_service.record_event.calls == [
            pretend.call(
                stub_user.id,
                tag="account:password:reset:attempt",
            )
        ]

    def test_redirect_authenticated_user(self):
        pyramid_request = pretend.stub(authenticated_userid=1)
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
                token=db_request.params["token"],
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

        now = datetime.datetime.utcnow()

        with freezegun.freeze_time(now):
            result = views.reset_password(db_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/account/login"
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                token=db_request.params["token"],
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
        now = pytz.UTC.localize(datetime.datetime.utcnow())
        later = now + datetime.timedelta(hours=1)
        data = {
            "action": "password-reset",
            "user.id": "8ad1a4ac-e016-11e6-bf01-fe55135034f3",
            "user.last_login": str(now),
        }
        token_service = pretend.stub(loads=pretend.call_recorder(lambda token: data))
        user = pretend.stub(last_login=later)
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
        now = pytz.UTC.localize(datetime.datetime.utcnow())
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
        pyramid_request = pretend.stub(authenticated_userid=1)
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
        user = UserFactory(is_active=False)
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
        assert db_request.route_path.calls == [pretend.call("manage.account")]
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

        db_request.user = user
        db_request.method = "POST"
        db_request.POST.update({"token": "RANDOM_KEY", "decline": "Decline"})
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
            pretend.call("manage.project.roles", project_name=project.name)
            if desired_role == "Owner"
            else pretend.call("packaging.project", name=project.name)
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

        form_obj = pretend.stub(
            next_route=pretend.stub(data=next_route),
            next_route_matchdict=pretend.stub(data="{}"),
            validate=lambda: True,
        )
        form_class = pretend.call_recorder(lambda d, **kw: form_obj)

        if next_route is not None:
            pyramid_request.method = "POST"
            pyramid_request.POST["next_route"] = next_route
            pyramid_request.POST["next_route_matchdict"] = "{}"

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
