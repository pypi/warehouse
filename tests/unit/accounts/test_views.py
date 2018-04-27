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
import uuid

import freezegun
import pretend
import pytest

from pyramid.httpexceptions import (HTTPMovedPermanently, HTTPSeeOther)
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts import views
from warehouse.accounts.interfaces import (
    IUserService, ITokenService, TokenExpired, TokenInvalid, TokenMissing,
    TooManyFailedLogins
)
from warehouse.admin.flags import AdminFlag

from ...common.db.accounts import EmailFactory, UserFactory


class TestFailedLoginView:
    exc = TooManyFailedLogins(resets_in=datetime.timedelta(seconds=600))
    request = pretend.stub()

    resp = views.failed_logins(exc, request)

    assert resp.status == "429 Too Many Failed Login Attempts"
    assert resp.detail == (
        "There have been too many unsuccessful login attempts. "
        "Try again later."
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
            pretend.call(username=user.username),
        ]

    def test_returns_user(self, db_request):
        user = UserFactory.create()
        assert views.profile(user, db_request) == {
            "user": user,
            "projects": [],
        }


class TestLogin:

    @pytest.mark.parametrize("next_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_form(self, pyramid_request, next_url):
        user_service = pretend.stub()
        pyramid_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
        )
        form_obj = pretend.stub()
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)

        if next_url is not None:
            pyramid_request.GET["next"] = next_url

        result = views.login(pyramid_request, _form_class=form_class)

        assert result == {
            "form": form_obj,
            "redirect": {"field": "next", "data": next_url},
        }
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
        ]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service),
        ]

    @pytest.mark.parametrize("next_url", [None, "/foo/bar/", "/wat/"])
    def test_post_invalid_returns_form(self, pyramid_request, next_url):
        user_service = pretend.stub()
        pyramid_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
        )
        pyramid_request.method = "POST"
        if next_url is not None:
            pyramid_request.POST["next"] = next_url
        form_obj = pretend.stub(validate=pretend.call_recorder(lambda: False))
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)

        result = views.login(pyramid_request, _form_class=form_class)
        assert pyramid_request.registry.datadog.increment.calls == [
            pretend.call('warehouse.authentication.start',
                         tags=['auth_method:login_form']),
            pretend.call('warehouse.authentication.failure',
                         tags=['auth_method:login_form']),
        ]

        assert result == {
            "form": form_obj,
            "redirect": {"field": "next", "data": next_url},
        }
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
        ]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service),
        ]
        assert form_obj.validate.calls == [pretend.call()]

    @pytest.mark.parametrize("with_user", [True, False])
    def test_post_validate_redirects(self, monkeypatch, pyramid_request,
                                     with_user):
        remember = pretend.call_recorder(
            lambda request, user_id: [("foo", "bar")]
        )
        monkeypatch.setattr(views, "remember", remember)

        new_session = {}

        user_id = uuid.uuid4()
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: user_id),
            update_user=pretend.call_recorder(lambda *a, **kw: None),
        )
        pyramid_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
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

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data="theuser"),
        )
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)

        pyramid_request.route_path = pretend.call_recorder(
            lambda a: '/the-redirect'
        )

        now = datetime.datetime.utcnow()

        with freezegun.freeze_time(now):
            result = views.login(pyramid_request, _form_class=form_class)

        assert pyramid_request.registry.datadog.increment.calls == [
            pretend.call('warehouse.authentication.start',
                         tags=['auth_method:login_form']),
            pretend.call('warehouse.authentication.complete',
                         tags=['auth_method:login_form']),
        ]

        assert isinstance(result, HTTPSeeOther)
        assert pyramid_request.route_path.calls == [
            pretend.call('manage.projects')
        ]
        assert result.headers["Location"] == "/the-redirect"
        assert result.headers["foo"] == "bar"

        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service),
        ]
        assert form_obj.validate.calls == [pretend.call()]

        assert user_service.find_userid.calls == [pretend.call("theuser")]
        assert user_service.update_user.calls == [
            pretend.call(user_id, last_login=now),
        ]

        if with_user:
            assert new_session == {}
        else:
            assert new_session == {"a": "b", "foo": "bar"}

        assert remember.calls == [pretend.call(pyramid_request, str(user_id))]
        assert pyramid_request.session.invalidate.calls == [pretend.call()]
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(IUserService, context=None),
        ]
        assert pyramid_request.session.new_csrf_token.calls == [pretend.call()]

    @pytest.mark.parametrize(
        # The set of all possible next URLs. Since this set is infinite, we
        # test only a finite set of reasonable URLs.
        ("expected_next_url, observed_next_url"),
        [
            ("/security/", "/security/"),
            ("http://example.com", "/the-redirect"),
        ],
    )
    def test_post_validate_no_redirects(self, pyramid_request,
                                        expected_next_url, observed_next_url):
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
            update_user=lambda *a, **k: None,
        )
        pyramid_request.find_service = pretend.call_recorder(
            lambda iface, context: user_service
        )
        pyramid_request.method = "POST"
        pyramid_request.POST["next"] = expected_next_url

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data="theuser"),
        )
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)
        pyramid_request.route_path = pretend.call_recorder(
            lambda a: '/the-redirect'
        )
        result = views.login(pyramid_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == observed_next_url

    def test_redirect_authenticated_user(self):
        pyramid_request = pretend.stub(authenticated_userid=1)
        pyramid_request.route_path = pretend.call_recorder(
            lambda a: '/the-redirect'
        )
        result = views.login(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestLogout:

    @pytest.mark.parametrize("next_url", [None, "/foo/bar/", "/wat/"])
    def test_get_returns_empty(self, pyramid_request, next_url):
        if next_url is not None:
            pyramid_request.GET["next"] = next_url

        assert views.logout(pyramid_request) == \
            {"redirect": {"field": "next", "data": next_url}}

    def test_post_forgets_user(self, monkeypatch, pyramid_request):
        forget = pretend.call_recorder(lambda request: [("foo", "bar")])
        monkeypatch.setattr(views, "forget", forget)

        pyramid_request.method = "POST"
        pyramid_request.session = pretend.stub(
            invalidate=pretend.call_recorder(lambda: None),
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
        [
            ("/security/", "/security/"),
            ("http://example.com", "/"),
        ],
    )
    def test_post_redirects_user(self, pyramid_request, expected_next_url,
                                 observed_next_url):
        pyramid_request.method = "POST"

        pyramid_request.POST["next"] = expected_next_url

        result = views.logout(pyramid_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == observed_next_url


class TestRegister:

    def test_get(self, db_request):
        form_inst = pretend.stub()
        form = pretend.call_recorder(lambda *args, **kwargs: form_inst)
        db_request.find_service = pretend.call_recorder(
            lambda *args, **kwargs: pretend.stub(
                enabled=False,
                csp_policy=pretend.stub(),
                merge=lambda _: None,
            )
        )
        result = views.register(db_request, _form_class=form)
        assert result["form"] is form_inst

    def test_redirect_authenticated_user(self):
        pyramid_request = pretend.stub(authenticated_userid=1)
        pyramid_request.route_path = pretend.call_recorder(
            lambda a: '/the-redirect'
        )
        result = views.register(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_register_honeypot(self, pyramid_request, monkeypatch):
        pyramid_request.method = "POST"
        create_user = pretend.call_recorder(lambda *args, **kwargs: None)
        add_email = pretend.call_recorder(lambda *args, **kwargs: None)
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.POST = {'confirm_form': 'fuzzywuzzy@bears.com'}
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, 'send_email_verification_email', send_email)

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
        db_request.find_service = pretend.call_recorder(
            lambda *args, **kwargs: pretend.stub(
                csp_policy={},
                merge=lambda _: {},
                enabled=False,
                verify_response=pretend.call_recorder(lambda _: None),
                find_userid=pretend.call_recorder(lambda _: None),
                find_userid_by_email=pretend.call_recorder(lambda _: None),
                update_user=lambda *args, **kwargs: None,
                create_user=create_user,
                add_email=add_email,
            )
        )
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.POST.update({
            "username": "username_value",
            "new_password": "MyStr0ng!shP455w0rd",
            "password_confirm": "MyStr0ng!shP455w0rd",
            "email": "foo@bar.com",
            "full_name": "full_name",
        })
        send_email = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(views, 'send_email_verification_email', send_email)

        result = views.register(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert create_user.calls == [
            pretend.call('username_value', 'full_name', 'MyStr0ng!shP455w0rd'),
        ]
        assert add_email.calls == [
            pretend.call(user.id, 'foo@bar.com', primary=True),
        ]
        assert send_email.calls == [pretend.call(db_request, user, email)]

    def test_register_fails_with_admin_flag_set(self, db_request):
        # This flag was already set via migration, just need to enable it
        flag = (
            db_request.db.query(AdminFlag)
            .get('disallow-new-user-registration')
        )
        flag.enabled = True

        db_request.method = "POST"

        db_request.POST.update({
            "username": "username_value",
            "password": "MyStr0ng!shP455w0rd",
            "password_confirm": "MyStr0ng!shP455w0rd",
            "email": "foo@bar.com",
            "full_name": "full_name",
        })

        db_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        db_request.route_path = pretend.call_recorder(lambda name: "/")

        result = views.register(db_request)

        assert isinstance(result, HTTPSeeOther)
        assert db_request.session.flash.calls == [
            pretend.call(
                ("New user registration temporarily disabled. "
                 "See https://pypi.org/help#admin-intervention for details."),
                queue="error"
            ),
        ]


class TestRequestPasswordReset:

    def test_get(self, pyramid_request, user_service):
        form_inst = pretend.stub()
        form_class = pretend.call_recorder(lambda *args, **kwargs: form_inst)
        pyramid_request.find_service = pretend.call_recorder(
            lambda *a, **kw: user_service,
        )
        pyramid_request.POST = pretend.stub()
        result = views.request_password_reset(
            pyramid_request,
            _form_class=form_class,
        )
        assert result["form"] is form_inst
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service),
        ]
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
        ]

    def test_request_password_reset(
            self, monkeypatch, pyramid_request, pyramid_config, user_service,
            token_service):

        stub_user = pretend.stub(username=pretend.stub())
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOK")
        user_service.get_user_by_username = pretend.call_recorder(
            lambda a: stub_user
        )
        pyramid_request.find_service = pretend.call_recorder(
            lambda interface, **kw: {
                IUserService: user_service,
                ITokenService: token_service,
            }[interface],
        )
        form_obj = pretend.stub(
            username_or_email=pretend.stub(data=stub_user.username),
            validate=pretend.call_recorder(lambda: True),
        )
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)
        n_hours = token_service.max_age // 60 // 60
        send_password_reset_email = pretend.call_recorder(
            lambda *args, **kwargs: {'n_hours': n_hours},
        )
        monkeypatch.setattr(
            views, 'send_password_reset_email', send_password_reset_email
        )

        result = views.request_password_reset(
            pyramid_request, _form_class=form_class
        )

        assert result == {'n_hours': n_hours}
        assert user_service.get_user_by_username.calls == [
            pretend.call(stub_user.username),
        ]
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name='password'),
        ]
        assert form_obj.validate.calls == [
            pretend.call(),
        ]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service),
        ]
        assert send_password_reset_email.calls == [
            pretend.call(pyramid_request, stub_user),
        ]

    def test_request_password_reset_with_email(
            self, monkeypatch, pyramid_request, pyramid_config, user_service,
            token_service):

        stub_user = pretend.stub(email=pretend.stub())
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOK")
        user_service.get_user_by_username = pretend.call_recorder(
            lambda a: None
        )
        user_service.get_user_by_email = pretend.call_recorder(
            lambda a: stub_user
        )
        pyramid_request.find_service = pretend.call_recorder(
            lambda interface, **kw: {
                IUserService: user_service,
                ITokenService: token_service,
            }[interface],
        )
        form_obj = pretend.stub(
            username_or_email=pretend.stub(data=stub_user.email),
            validate=pretend.call_recorder(lambda: True),
        )
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)
        n_hours = token_service.max_age // 60 // 60
        send_password_reset_email = pretend.call_recorder(
            lambda *args, **kwargs: {'n_hours': n_hours},
        )
        monkeypatch.setattr(
            views, 'send_password_reset_email', send_password_reset_email
        )

        result = views.request_password_reset(
            pyramid_request, _form_class=form_class
        )

        assert result == {'n_hours': n_hours}
        assert user_service.get_user_by_username.calls == [
            pretend.call(stub_user.email),
        ]
        assert user_service.get_user_by_email.calls == [
            pretend.call(stub_user.email),
        ]
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name='password'),
        ]
        assert form_obj.validate.calls == [
            pretend.call(),
        ]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service),
        ]
        assert send_password_reset_email.calls == [
            pretend.call(pyramid_request, stub_user),
        ]

    def test_request_password_reset_with_wrong_credentials(
            self, monkeypatch, pyramid_request, pyramid_config, user_service,
            token_service):

        stub_user = pretend.stub(username=pretend.stub())
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOK")
        user_service.get_user_by_username = pretend.call_recorder(
            lambda a: None
        )
        user_service.get_user_by_email = pretend.call_recorder(
            lambda a: None
        )
        pyramid_request.find_service = pretend.call_recorder(
            lambda interface, **kw: {
                IUserService: user_service,
                ITokenService: token_service,
            }[interface],
        )
        form_obj = pretend.stub(
            username_or_email=pretend.stub(data=stub_user.username),
            validate=pretend.call_recorder(lambda: True),
        )
        form_class = pretend.call_recorder(lambda d, user_service: form_obj)
        n_hours = token_service.max_age // 60 // 60
        send_password_reset_email = pretend.call_recorder(
            lambda *args, **kwargs: {'n_hours': n_hours},
        )
        monkeypatch.setattr(
            views, 'send_password_reset_email', send_password_reset_email
        )

        result = views.request_password_reset(
            pyramid_request, _form_class=form_class
        )

        assert result == {'n_hours': n_hours}
        assert user_service.get_user_by_username.calls == [
            pretend.call(stub_user.username),
        ]
        assert user_service.get_user_by_email.calls == [
            pretend.call(stub_user.username),
        ]
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name='password'),
        ]
        assert form_obj.validate.calls == [
            pretend.call(),
        ]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, user_service=user_service),
        ]
        assert send_password_reset_email.calls == [
            pretend.call(pyramid_request, None)
        ]

    def test_redirect_authenticated_user(self):
        pyramid_request = pretend.stub(authenticated_userid=1)
        pyramid_request.route_path = pretend.call_recorder(
            lambda a: '/the-redirect'
        )
        result = views.request_password_reset(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestResetPassword:

    def test_get(self, db_request, user_service, token_service):
        user = UserFactory.create()
        form_inst = pretend.stub()
        form_class = pretend.call_recorder(lambda *args, **kwargs: form_inst)

        db_request.GET.update({"token": "RANDOM_KEY"})
        token_service.loads = pretend.call_recorder(
            lambda token: {
                'action': 'password-reset',
                'user.id': str(user.id),
                'user.last_login': str(user.last_login),
                'user.password_date': str(user.password_date),
            }
        )
        db_request.find_service = pretend.call_recorder(
            lambda interface, **kwargs: {
                IUserService: user_service,
                ITokenService: token_service,
            }[interface]
        )

        result = views.reset_password(db_request, _form_class=form_class)

        assert result["form"] is form_inst
        assert form_class.calls == [
            pretend.call(
                token=db_request.params['token'],
                username=user.username,
                full_name=user.name,
                email=user.email,
                user_service=user_service,
            )
        ]
        assert token_service.loads.calls == [
            pretend.call("RANDOM_KEY"),
        ]
        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name="password"),
        ]

    def test_reset_password(self, db_request, user_service, token_service):
        user = UserFactory.create()
        db_request.method = "POST"
        db_request.POST.update({"token": "RANDOM_KEY"})
        form_obj = pretend.stub(
            new_password=pretend.stub(data="password_value"),
            validate=pretend.call_recorder(lambda *args: True)
        )

        form_class = pretend.call_recorder(lambda *args, **kwargs: form_obj)

        db_request.route_path = pretend.call_recorder(lambda name: "/")
        token_service.loads = pretend.call_recorder(
            lambda token: {
                'action': 'password-reset',
                'user.id': str(user.id),
                'user.last_login': str(user.last_login),
                'user.password_date': str(user.password_date),
            }
        )
        user_service.update_user = pretend.call_recorder(lambda *a, **kw: None)
        db_request.find_service = pretend.call_recorder(
            lambda interface, **kwargs: {
                IUserService: user_service,
                ITokenService: token_service,
            }[interface]
        )
        db_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        now = datetime.datetime.utcnow()

        with freezegun.freeze_time(now):
            result = views.reset_password(db_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert form_obj.validate.calls == [pretend.call()]
        assert form_class.calls == [
            pretend.call(
                token=db_request.params['token'],
                username=user.username,
                full_name=user.name,
                email=user.email,
                user_service=user_service
            ),
        ]
        assert db_request.route_path.calls == [pretend.call('index')]
        assert token_service.loads.calls == [
            pretend.call('RANDOM_KEY'),
        ]
        assert user_service.update_user.calls == [
            pretend.call(user.id, password=form_obj.new_password.data),
            pretend.call(user.id, last_login=now),
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                "You have successfully reset your password", queue="success"
            ),
        ]
        assert db_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(ITokenService, name="password"),
            pretend.call(IUserService, context=None),
        ]

    @pytest.mark.parametrize(
        ("exception", "message"),
        [
            (
                TokenInvalid,
                "Invalid token - request a new password reset link",
            ), (
                TokenExpired,
                "Expired token - request a new password reset link",
            ), (
                TokenMissing,
                "Invalid token - no token supplied"
            ),
        ],
    )
    def test_reset_password_loads_failure(
            self, pyramid_request, exception, message):

        def loads(token):
            raise exception

        pyramid_request.find_service = lambda interface, **kwargs: {
            IUserService: pretend.stub(),
            ITokenService: pretend.stub(loads=loads),
        }[interface]
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        views.reset_password(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call('accounts.request-password-reset'),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(message, queue='error'),
        ]

    def test_reset_password_invalid_action(self, pyramid_request):
        data = {
            'action': 'invalid-action',
        }
        token_service = pretend.stub(
            loads=pretend.call_recorder(lambda token: data),
        )
        pyramid_request.find_service = lambda interface, **kwargs: {
            IUserService: pretend.stub(),
            ITokenService: token_service,
        }[interface]
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        views.reset_password(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call('accounts.request-password-reset'),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Invalid token - not a password reset token", queue='error'
            ),
        ]

    def test_reset_password_invalid_user(self, pyramid_request):
        data = {
            'action': 'password-reset',
            'user.id': '8ad1a4ac-e016-11e6-bf01-fe55135034f3',
        }
        token_service = pretend.stub(
            loads=pretend.call_recorder(lambda token: data),
        )
        user_service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: None),
        )
        pyramid_request.find_service = lambda interface, **kwargs: {
            IUserService: user_service,
            ITokenService: token_service,
        }[interface]
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        views.reset_password(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call('accounts.request-password-reset'),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Invalid token - user not found", queue='error'
            ),
        ]
        assert user_service.get_user.calls == [
            pretend.call(uuid.UUID(data['user.id'])),
        ]

    def test_reset_password_last_login_changed(self, pyramid_request):
        now = datetime.datetime.utcnow()
        later = now + datetime.timedelta(hours=1)
        data = {
            'action': 'password-reset',
            'user.id': '8ad1a4ac-e016-11e6-bf01-fe55135034f3',
            'user.last_login': str(now),
        }
        token_service = pretend.stub(
            loads=pretend.call_recorder(lambda token: data),
        )
        user = pretend.stub(last_login=later)
        user_service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: user),
        )
        pyramid_request.find_service = lambda interface, **kwargs: {
            IUserService: user_service,
            ITokenService: token_service,
        }[interface]
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        views.reset_password(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call('accounts.request-password-reset'),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Invalid token - user has logged in since this token was "
                "requested",
                queue='error',
            ),
        ]

    def test_reset_password_password_date_changed(self, pyramid_request):
        now = datetime.datetime.utcnow()
        later = now + datetime.timedelta(hours=1)
        data = {
            'action': 'password-reset',
            'user.id': '8ad1a4ac-e016-11e6-bf01-fe55135034f3',
            'user.last_login': str(now),
            'user.password_date': str(now),
        }
        token_service = pretend.stub(
            loads=pretend.call_recorder(lambda token: data),
        )
        user = pretend.stub(last_login=now, password_date=later)
        user_service = pretend.stub(
            get_user=pretend.call_recorder(lambda userid: user),
        )
        pyramid_request.find_service = lambda interface, **kwargs: {
            IUserService: user_service,
            ITokenService: token_service,
        }[interface]
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        views.reset_password(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call('accounts.request-password-reset'),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Invalid token - password has already been changed since this "
                "token was requested",
                queue='error',
            ),
        ]

    def test_redirect_authenticated_user(self):
        pyramid_request = pretend.stub(authenticated_userid=1)
        pyramid_request.route_path = pretend.call_recorder(
            lambda a: '/the-redirect'
        )
        result = views.reset_password(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestVerifyEmail:

    @pytest.mark.parametrize(
        ("is_primary", "confirm_message"),
        [
            (True, "This is your primary address."),
            (False, "You can now set this email as your primary address."),
        ]
    )
    def test_verify_email(
            self, db_request, user_service, token_service, is_primary,
            confirm_message):
        user = UserFactory(is_active=False)
        email = EmailFactory(user=user, verified=False, primary=is_primary)
        db_request.user = user
        db_request.GET.update({"token": "RANDOM_KEY"})
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        token_service.loads = pretend.call_recorder(
            lambda token: {
                'action': 'email-verify',
                'email.id': str(email.id),
            }
        )
        db_request.find_service = pretend.call_recorder(
            lambda *a, **kwargs: token_service,
        )
        db_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        result = views.verify_email(db_request)

        db_request.db.flush()
        assert email.verified
        assert user.is_active
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
        assert db_request.route_path.calls == [pretend.call('manage.account')]
        assert token_service.loads.calls == [pretend.call('RANDOM_KEY')]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Email address {email.email} verified. " +
                confirm_message,
                queue="success"
            ),
        ]
        assert db_request.find_service.calls == [
            pretend.call(ITokenService, name="email"),
        ]

    @pytest.mark.parametrize(
        ("exception", "message"),
        [
            (
                TokenInvalid,
                "Invalid token - request a new verification link",
            ), (
                TokenExpired,
                "Expired token - request a new verification link",
            ), (
                TokenMissing,
                "Invalid token - no token supplied"
            ),
        ],
    )
    def test_verify_email_loads_failure(
            self, pyramid_request, exception, message):

        def loads(token):
            raise exception

        pyramid_request.find_service = (
            lambda *a, **kw: pretend.stub(loads=loads)
        )
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        views.verify_email(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call('manage.account'),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(message, queue='error'),
        ]

    def test_verify_email_invalid_action(self, pyramid_request):
        data = {
            'action': 'invalid-action',
        }
        pyramid_request.find_service = (
            lambda *a, **kw: pretend.stub(loads=lambda a: data)
        )
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        views.verify_email(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call('manage.account'),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call(
                "Invalid token - not an email verification token",
                queue='error',
            ),
        ]

    def test_verify_email_not_found(self, pyramid_request):
        data = {
            'action': 'email-verify',
            'email.id': 'invalid',
        }
        pyramid_request.find_service = (
            lambda *a, **kw: pretend.stub(loads=lambda a: data)
        )
        pyramid_request.params = {"token": "RANDOM_KEY"}
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        def raise_no_result(*a):
            raise NoResultFound

        pyramid_request.db = pretend.stub(query=raise_no_result)

        views.verify_email(pyramid_request)

        assert pyramid_request.route_path.calls == [
            pretend.call('manage.account'),
        ]
        assert pyramid_request.session.flash.calls == [
            pretend.call('Email not found', queue='error')
        ]

    def test_verify_email_already_verified(self, db_request):
        user = UserFactory()
        email = EmailFactory(user=user, verified=True)
        data = {
            'action': 'email-verify',
            'email.id': email.id,
        }
        db_request.user = user
        db_request.find_service = (
            lambda *a, **kw: pretend.stub(loads=lambda a: data)
        )
        db_request.params = {"token": "RANDOM_KEY"}
        db_request.route_path = pretend.call_recorder(lambda name: "/")
        db_request.session.flash = pretend.call_recorder(
            lambda *a, **kw: None
        )

        views.verify_email(db_request)

        assert db_request.route_path.calls == [
            pretend.call('manage.account'),
        ]
        assert db_request.session.flash.calls == [
            pretend.call('Email already verified', queue='error')
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

        assert views.edit_profile_button(user, request) == {'user': user}
