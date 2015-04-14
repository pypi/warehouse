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
from warehouse.accounts.interfaces import ILoginService

from ..common.db.accounts import UserFactory


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
        assert views.profile(user, db_request) == {"user": user}


class TestLogin:

    def test_get_returns_form(self, pyramid_request):
        login_service = pretend.stub()
        pyramid_request.find_service = pretend.call_recorder(
            lambda iface, context: login_service
        )
        form_obj = pretend.stub()
        form_class = pretend.call_recorder(lambda d, login_service: form_obj)

        result = views.login(pyramid_request, _form_class=form_class)

        assert result == {"form": form_obj}
        assert pyramid_request.find_service.calls == [
            pretend.call(ILoginService, context=None),
        ]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, login_service=login_service),
        ]

    def test_post_invalid_returns_form(self, pyramid_request):
        login_service = pretend.stub()
        pyramid_request.find_service = pretend.call_recorder(
            lambda iface, context: login_service
        )
        pyramid_request.method = "POST"
        form_obj = pretend.stub(validate=pretend.call_recorder(lambda: False))
        form_class = pretend.call_recorder(lambda d, login_service: form_obj)

        result = views.login(pyramid_request, _form_class=form_class)

        assert result == {"form": form_obj}
        assert pyramid_request.find_service.calls == [
            pretend.call(ILoginService, context=None),
        ]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, login_service=login_service),
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

        login_service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: 1),
        )
        pyramid_request.find_service = pretend.call_recorder(
            lambda iface, context: login_service
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

        route_path = lambda route_name, username: "/accounts/{}/".\
                                                  format(username)
        # TODO: Why must I mock this request method? Why is the original
        # route_path on the request object not already aware of routes?
        pyramid_request.route_path = pretend.call_recorder(route_path)

        username = "theuser"
        form_obj = pretend.stub(
            validate=pretend.call_recorder(lambda: True),
            username=pretend.stub(data=username),
        )
        form_class = pretend.call_recorder(lambda d, login_service: form_obj)

        result = views.login(pyramid_request, _form_class=form_class)

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == route_path("accounts.profile",
                                                        username)
        assert result.headers["foo"] == "bar"
        assert pyramid_request.find_service.calls == [
            pretend.call(ILoginService, context=None),
        ]
        assert form_class.calls == [
            pretend.call(pyramid_request.POST, login_service=login_service),
        ]
        assert form_obj.validate.calls == [pretend.call()]
        assert login_service.find_userid.calls == [pretend.call("theuser")]
        if with_user:
            assert new_session == {}
        else:
            assert new_session == {"a": "b", "foo": "bar"}
        assert pyramid_request.session.invalidate.calls == [pretend.call()]
        assert remember.calls == [pretend.call(pyramid_request, 1)]
        assert pyramid_request.session.new_csrf_token.calls == [pretend.call()]


class TestLogout:

    def test_get_returns_empty(self, pyramid_request):
        assert views.logout(pyramid_request) == {}

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
