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

import json

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
            params={},
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

    @pytest.mark.parametrize(
        ("require_reauth", "needs_reauth_calls"),
        [
            (True, [pretend.call(manage.DEFAULT_TIME_TO_REAUTH)]),
            (666, [pretend.call(666)]),
        ],
    )
    def test_reauth_view_with_malformed_errors(
        self, monkeypatch, require_reauth, needs_reauth_calls
    ):
        mock_user_service = pretend.stub()
        response = pretend.stub()

        def mock_response(*args, **kwargs):
            return {"mock_key": "mock_response"}

        def mock_form(*args, **kwargs):
            return pretend.stub(password=pretend.stub(errors=[]))

        monkeypatch.setattr(manage, "render_to_response", mock_response)
        monkeypatch.setattr(manage, "ReAuthenticateForm", mock_form)

        context = pretend.stub()
        dummy_request = pretend.stub(
            session=pretend.stub(
                needs_reauthentication=pretend.call_recorder(lambda *a: True)
            ),
            params={"errors": "{this is not: valid json"},
            POST={},
            user=pretend.stub(username="fakeuser"),
            matched_route=pretend.stub(name="fake.route"),
            matchdict={"foo": "bar"},
            GET=pretend.stub(mixed=lambda: {"baz": "qux"}),
            find_service=lambda service, context=None: mock_user_service,
        )

        @pretend.call_recorder
        def view(context, request):
            return response

        info = pretend.stub(options={"require_reauth": True}, exception_only=False)

        derived_view = manage.reauth_view(view, info)

        assert derived_view(context, dummy_request) is not response
        assert mock_form().password.errors == []

    def test_reauth_view_sets_errors(self, monkeypatch):
        mock_field = pretend.stub(errors=[])
        form = pretend.stub(password=mock_field)
        response = pretend.stub()

        monkeypatch.setattr(manage, "ReAuthenticateForm", lambda *a, **kw: form)
        monkeypatch.setattr(manage, "render_to_response", lambda *a, **kw: {})

        request = pretend.stub(
            session=pretend.stub(needs_reauthentication=lambda *a: True),
            params={
                "errors": json.dumps({"password": ["Invalid password"]})
            },  # mock errors
            POST={},
            GET=pretend.stub(mixed=lambda: {}),
            matched_route=pretend.stub(name="reauth"),
            matchdict={},
            user=pretend.stub(username="tester"),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        context = pretend.stub()
        info = pretend.stub(options={"require_reauth": True})

        @pretend.call_recorder
        def view(context, request):
            return response

        wrapped = manage.reauth_view(view, info)

        wrapped(context, request)

        assert mock_field.errors == [
            "Invalid password"
        ], f"Expected errors to be ['Invalid password'], but got {mock_field.errors}"

    def test_reauth_view_field_missing_or_no_errors(self, monkeypatch):
        mock_user_service = pretend.stub()
        response = pretend.stub()

        def mock_response(*args, **kwargs):
            return {"mock_key": "mock_response"}

        class DummyField:
            pass  # No `errors` attribute

        class DummyForm:
            def __init__(self, *args, **kwargs):
                self.existing_field = DummyField()  # Has no `.errors`

        monkeypatch.setattr(manage, "render_to_response", mock_response)
        monkeypatch.setattr(manage, "ReAuthenticateForm", DummyForm)

        context = pretend.stub()
        dummy_request = pretend.stub(
            session=pretend.stub(
                needs_reauthentication=pretend.call_recorder(lambda *a: True)
            ),
            params={
                "errors": json.dumps(
                    {"non_existing_field": ["err1"], "existing_field": ["err2"]}
                )
            },
            POST={},
            user=pretend.stub(username="fakeuser"),
            matched_route=pretend.stub(name="fake.route"),
            matchdict={"foo": "bar"},
            GET=pretend.stub(mixed=lambda: {"baz": "qux"}),
            find_service=lambda service, context=None: mock_user_service,
        )

        @pretend.call_recorder
        def view(context, request):
            return response

        info = pretend.stub(options={"require_reauth": True}, exception_only=False)

        derived_view = manage.reauth_view(view, info)
        result = derived_view(context, dummy_request)

        assert isinstance(result, dict)
        assert result["mock_key"] == "mock_response"


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
