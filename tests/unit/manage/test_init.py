# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from warehouse import manage


class TestReAuthView:
    def test_has_options(self):
        assert set(manage.reauth_view.options) == {"require_reauth"}

    @pytest.mark.parametrize(
        ("require_reauth", "needs_reauth_calls"),
        [
            (True, [pretend.call(manage.DEFAULT_TIME_TO_REAUTH)]),
            (666, [pretend.call(666)]),
            (False, []),
            (None, []),
        ],
    )
    def test_unneeded_reauth(self, require_reauth, needs_reauth_calls):
        context = pretend.stub()
        request = pretend.stub(
            matchdict="{}",
            session=pretend.stub(
                needs_reauthentication=pretend.call_recorder(lambda *args: False)
            ),
        )
        response = pretend.stub()

        @pretend.call_recorder
        def view(context, request):
            return response

        info = pretend.stub(options={}, exception_only=False)
        info.options["require_reauth"] = require_reauth
        derived_view = manage.reauth_view(view, info)

        assert derived_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]
        assert request.session.needs_reauthentication.calls == needs_reauth_calls

    @pytest.mark.parametrize(
        ("require_reauth", "needs_reauth_calls"),
        [
            (True, [pretend.call(manage.DEFAULT_TIME_TO_REAUTH)]),
            (666, [pretend.call(666)]),
        ],
    )
    def test_reauth(self, monkeypatch, require_reauth, needs_reauth_calls):
        context = pretend.stub()
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda service, context: pretend.stub()),
            POST=pretend.stub(),
            session=pretend.stub(
                needs_reauthentication=pretend.call_recorder(lambda *args: True)
            ),
            user=pretend.stub(username=pretend.stub()),
            matched_route=pretend.stub(name=pretend.stub()),
            matchdict={"foo": "bar"},
            GET=pretend.stub(mixed=lambda: {"baz": "bar"}),
        )
        response = pretend.stub()

        def mock_response(*args, **kwargs):
            return {"mock_key": "mock_response"}

        def mock_form(*args, **kwargs):
            return pretend.stub()

        monkeypatch.setattr(manage, "render_to_response", mock_response)
        monkeypatch.setattr(manage, "ReAuthenticateForm", mock_form)

        @pretend.call_recorder
        def view(context, request):
            return response

        info = pretend.stub(options={}, exception_only=False)
        info.options["require_reauth"] = require_reauth
        derived_view = manage.reauth_view(view, info)

        assert derived_view(context, request) is not response
        assert view.calls == []
        assert request.session.needs_reauthentication.calls == needs_reauth_calls


def test_includeme(monkeypatch):
    settings = {
        "warehouse.manage.oidc.user_registration_ratelimit_string": "10 per day",
        "warehouse.manage.oidc.ip_registration_ratelimit_string": "100 per day",
    }

    config = pretend.stub(
        add_view_deriver=pretend.call_recorder(lambda f, over, under: None),
        register_service_factory=pretend.call_recorder(lambda s, i, **kw: None),
        registry=pretend.stub(
            settings=pretend.stub(get=pretend.call_recorder(lambda k: settings.get(k)))
        ),
    )

    rate_limit_class = pretend.call_recorder(lambda s: s)
    rate_limit_iface = pretend.stub()
    monkeypatch.setattr(manage, "RateLimit", rate_limit_class)
    monkeypatch.setattr(manage, "IRateLimiter", rate_limit_iface)

    manage.includeme(config)

    assert config.add_view_deriver.calls == [
        pretend.call(manage.reauth_view, over="rendered_view", under="decorated_view")
    ]
    assert config.register_service_factory.calls == [
        pretend.call(
            "10 per day", rate_limit_iface, name="user_oidc.publisher.register"
        ),
        pretend.call(
            "100 per day", rate_limit_iface, name="ip_oidc.publisher.register"
        ),
    ]
    assert config.registry.settings.get.calls == [
        pretend.call("warehouse.manage.oidc.user_registration_ratelimit_string"),
        pretend.call("warehouse.manage.oidc.ip_registration_ratelimit_string"),
    ]
