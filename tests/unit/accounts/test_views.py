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

import pretend
import pytest

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPSeeOther

from warehouse.accounts import views
from warehouse.accounts.interfaces import IUserService

from ...common.db.accounts import UserFactory


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
        recaptcha_service = pretend.stub(
            merge=pretend.call_recorder(lambda _: None),
            csp_policy={},
        )
        pyramid_request.find_service = pretend.call_recorder(
            lambda iface=None, context=None, name=None:
                user_service if name is None else recaptcha_service
        )
        form_obj = pretend.stub()
        form_class = pretend.call_recorder(
            lambda data=None, user_service=None,
            recaptcha_service=None: form_obj
        )

        if next_url is not None:
            pyramid_request.GET["next"] = next_url

        result = views.login(pyramid_request, _form_class=form_class)

        assert result == {
            "form": form_obj,
            "redirect": {"field": "next", "data": next_url},
        }
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(name="recaptcha"),
            pretend.call(name="csp"),
        ]
        assert form_class.calls == [
            pretend.call(
                data=pyramid_request.POST,
                user_service=user_service,
                recaptcha_service=recaptcha_service
            ),
        ]

    @pytest.mark.parametrize("next_url", [None, "/foo/bar/", "/wat/"])
    def test_post_invalid_returns_form(self, pyramid_request, next_url):
        user_service = pretend.stub()
        recaptcha_service = pretend.stub(
            merge=pretend.call_recorder(lambda _: None),
            csp_policy={},
        )
        pyramid_request.find_service = pretend.call_recorder(
            lambda iface=None, context=None, name=None:
                user_service if name is None else recaptcha_service
        )
        pyramid_request.method = "POST"
        if next_url is not None:
            pyramid_request.POST["next"] = next_url
        form_obj = pretend.stub(validate=pretend.call_recorder(lambda: False))
        form_class = pretend.call_recorder(
            lambda data=None, user_service=None,
            recaptcha_service=None: form_obj
        )

        result = views.login(pyramid_request, _form_class=form_class)

        assert result == {
            "form": form_obj,
            "redirect": {"field": "next", "data": next_url},
        }
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(name="recaptcha"),
            pretend.call(name="csp"),
        ]
        assert form_class.calls == [
            pretend.call(
                data=pyramid_request.POST,
                user_service=user_service,
                recaptcha_service=recaptcha_service
            ),
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

        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
        )
        recaptcha_service = pretend.stub(
            merge=pretend.call_recorder(lambda _: None),
            csp_policy={},
        )
        pyramid_request.find_service = pretend.call_recorder(
            lambda iface=None, context=None, name=None:
                user_service if name is None else recaptcha_service
        )
        pyramid_request.method = "POST"
        pyramid_request.session = pretend.stub(
            items=lambda: [("a", "b"), ("foo", "bar")],
            update=new_session.update,
            invalidate=pretend.call_recorder(lambda: None),
            new_csrf_token=pretend.call_recorder(lambda: None),
        )

        pyramid_request.set_property(
            lambda r: 1234 if with_user else None,
            name="unauthenticated_userid",
        )

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data="theuser"),
        )
        form_class = pretend.call_recorder(
            lambda data=None, user_service=None,
            recaptcha_service=None: form_obj
        )

        result = views.login(pyramid_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)

        assert result.headers["Location"] == "/"
        assert result.headers["foo"] == "bar"

        assert form_class.calls == [
            pretend.call(
                data=pyramid_request.POST,
                user_service=user_service,
                recaptcha_service=recaptcha_service,
            ),
        ]
        assert form_obj.validate.calls == [pretend.call()]

        assert user_service.find_userid.calls == [pretend.call("theuser")]

        if with_user:
            assert new_session == {}
        else:
            assert new_session == {"a": "b", "foo": "bar"}

        assert remember.calls == [pretend.call(pyramid_request, 1)]
        assert pyramid_request.session.invalidate.calls == [pretend.call()]
        assert pyramid_request.find_service.calls == [
            pretend.call(IUserService, context=None),
            pretend.call(name="recaptcha"),
            pretend.call(name="csp"),
        ]
        assert pyramid_request.session.new_csrf_token.calls == [pretend.call()]

    @pytest.mark.parametrize(
        # The set of all possible next URLs. Since this set is infinite, we
        # test only a finite set of reasonable URLs.
        ("expected_next_url, observed_next_url"),
        [
            ("/security/", "/security/"),
            ("http://example.com", "/"),
        ],
    )
    def test_post_validate_no_redirects(self, pyramid_request,
                                        expected_next_url, observed_next_url):
        user_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
        )
        recaptcha_service = pretend.stub(
            merge=pretend.call_recorder(lambda _: None),
            csp_policy={},
        )
        pyramid_request.find_service = pretend.call_recorder(
            lambda iface=None, context=None, name=None:
                user_service if name is None else recaptcha_service
        )
        pyramid_request.method = "POST"
        pyramid_request.POST["next"] = expected_next_url

        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data="theuser"),
        )
        form_class = pretend.call_recorder(
            lambda data=None, user_service=None,
            recaptcha_service=None: form_obj
        )

        result = views.login(pyramid_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)

        assert result.headers["Location"] == observed_next_url


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
    def test_get(self, pyramid_request):
        form_inst = pretend.stub()
        form = pretend.call_recorder(lambda *args, **kwargs: form_inst)
        pyramid_request.find_service = pretend.call_recorder(
            lambda *args, **kwargs: pretend.stub(
                enabled=False,
                csp_policy=pretend.stub(),
                merge=lambda _: None,
            )
        )
        result = views.register(pyramid_request, _form_class=form)
        assert result["form"] is form_inst

    def test_redirect_authenticated_user(self):
        result = views.register(pretend.stub(authenticated_userid=1))
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"

    def test_register_redirect(self, pyramid_request):
        pyramid_request.method = "POST"
        pyramid_request.find_service = pretend.call_recorder(
            lambda *args, **kwargs: pretend.stub(
                csp_policy={},
                merge=lambda _: {},
                enabled=False,
                verify_response=pretend.call_recorder(lambda _: None),
                find_userid=pretend.call_recorder(lambda _: None),
                find_userid_by_email=pretend.call_recorder(lambda _: None),
                create_user=pretend.call_recorder(
                    lambda *args, **kwargs: pretend.stub(id=1),
                ),
            )
        )
        pyramid_request.route_path = pretend.call_recorder(lambda name: "/")
        pyramid_request.POST.update({
            "username": "username_value",
            "password": "MyStr0ng!shP455w0rd",
            "password_confirm": "MyStr0ng!shP455w0rd",
            "email": "foo@bar.com",
            "full_name": "full_name",
        })

        result = views.register(pyramid_request)
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/"
