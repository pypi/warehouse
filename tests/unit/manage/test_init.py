# SPDX-License-Identifier: Apache-2.0

import json
import types

import pytest

from webob.multidict import MultiDict

from warehouse import manage
from warehouse.sessions import Session

from ...common.db.accounts import UserFactory


class TestReAuthView:
    def test_has_options(self):
        assert set(manage.reauth_view.options) == {"require_reauth"}

    @pytest.mark.parametrize("require_reauth", [False, None])
    def test_reauth_not_required(self, mocker, require_reauth):
        view = mocker.sentinel.view
        info = types.SimpleNamespace(options={"require_reauth": require_reauth})

        assert manage.reauth_view(view, info) is view

    @pytest.mark.parametrize(
        ("require_reauth", "time_to_reauth"),
        [
            (True, manage.DEFAULT_TIME_TO_REAUTH),
            (666, 666),
        ],
    )
    def test_unneeded_reauth(
        self, mocker, pyramid_request, require_reauth, time_to_reauth
    ):
        pyramid_request.session = Session()
        pyramid_request.session.record_auth_timestamp()
        needs_reauthentication = mocker.spy(
            pyramid_request.session, "needs_reauthentication"
        )
        context = mocker.sentinel.context
        view = mocker.Mock(__name__="view")

        info = types.SimpleNamespace(options={"require_reauth": require_reauth})
        derived_view = manage.reauth_view(view, info)

        assert derived_view(context, pyramid_request) is view.return_value
        view.assert_called_once_with(context, pyramid_request)
        needs_reauthentication.assert_called_once_with(time_to_reauth)

    @pytest.mark.parametrize(
        ("require_reauth", "time_to_reauth"),
        [
            (True, manage.DEFAULT_TIME_TO_REAUTH),
            (666, 666),
        ],
    )
    def test_reauth(
        self, mocker, pyramid_request, user_service, require_reauth, time_to_reauth
    ):
        pyramid_request.session = Session()
        needs_reauthentication = mocker.spy(
            pyramid_request.session, "needs_reauthentication"
        )
        pyramid_request.user = UserFactory.build()
        pyramid_request.matched_route = types.SimpleNamespace(name="manage.account")
        pyramid_request.matchdict = {"foo": "bar"}
        pyramid_request.POST = MultiDict()
        pyramid_request.GET = MultiDict({"baz": "bar"})

        render_to_response = mocker.patch.object(
            manage, "render_to_response", autospec=True
        )
        form_class = mocker.patch.object(manage, "ReAuthenticateForm", autospec=True)
        view = mocker.Mock(__name__="view")

        info = types.SimpleNamespace(options={"require_reauth": require_reauth})
        derived_view = manage.reauth_view(view, info)

        assert (
            derived_view(mocker.sentinel.context, pyramid_request)
            is render_to_response.return_value
        )
        view.assert_not_called()
        needs_reauthentication.assert_called_once_with(time_to_reauth)
        form_class.assert_called_once_with(
            pyramid_request.POST,
            request=pyramid_request,
            user_id=pyramid_request.user.id,
            next_route="manage.account",
            next_route_matchdict=json.dumps({"foo": "bar"}),
            next_route_query=json.dumps({"baz": "bar"}),
            user_service=user_service,
        )
        render_to_response.assert_called_once_with(
            "re-auth.html",
            {"form": form_class.return_value, "user": pyramid_request.user},
            request=pyramid_request,
        )


def test_includeme(mocker):
    config = mocker.Mock(spec=["add_view_deriver", "register_rate_limiter"])
    config.registry = types.SimpleNamespace(
        settings={
            "warehouse.manage.oidc.user_registration_ratelimit_string": "10 per day",
            "warehouse.manage.oidc.ip_registration_ratelimit_string": "100 per day",
        }
    )

    manage.includeme(config)

    config.add_view_deriver.assert_called_once_with(
        manage.reauth_view, over="rendered_view", under="decorated_view"
    )
    assert config.register_rate_limiter.call_args_list == [
        mocker.call("10 per day", "user_oidc.publisher.register"),
        mocker.call("100 per day", "ip_oidc.publisher.register"),
    ]
