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
import json

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
    def test_reauth_with_errors_param(self, monkeypatch, require_reauth, needs_reauth_calls):
        context = pretend.stub()

        class FakeField:
            def __init__(self):
                self.errors = []

        class FakeForm:
            def __init__(self, *args, **kwargs):
                self.password = FakeField()

        request = pretend.stub(
            find_service=pretend.call_recorder(lambda service, context: pretend.stub()),
            POST=pretend.stub(),
            session=pretend.stub(
                needs_reauthentication=pretend.call_recorder(lambda *args: True)
            ),
            params={"errors": json.dumps({"password": ["Invalid password."]})},
            user=pretend.stub(username="test_user"),
            matched_route=pretend.stub(name="some_route"),
            matchdict={"foo": "bar"},
            GET=pretend.stub(mixed=lambda: {"baz": "qux"}),
        )

        monkeypatch.setattr(manage, "render_to_response", lambda tpl, ctx, request: ctx)
        monkeypatch.setattr(manage, "ReAuthenticateForm", lambda *a, **kw: FakeForm())

        @pretend.call_recorder
        def view(context, request):
            raise AssertionError("View should not be called when reauth is needed")

        info = pretend.stub(options={"require_reauth": True}, exception_only=False)
        derived_view = manage.reauth_view(view, info)

        result = derived_view(context, request)
        # Ensure error message is correctly set in the form field
        assert result["form"].password.errors == ["Invalid password."]

    @pytest.mark.parametrize(
        ("require_reauth", "needs_reauth_calls"),
        [
            (True, [pretend.call(manage.DEFAULT_TIME_TO_REAUTH)]),
            (666, [pretend.call(666)]),
        ],
    )
    def test_reauth_view_with_malformed_errors(self, monkeypatch, require_reauth, needs_reauth_calls):
        mock_user_service = pretend.stub()
        mock_form = pretend.stub(password=pretend.stub(errors=[]))

        monkeypatch.setattr(manage, "ReAuthenticateForm", lambda *a, **k: mock_form)
        monkeypatch.setattr(manage, "render_to_response", lambda tpl, context, request=None: context)

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

        view = lambda context, request: None
        info = pretend.stub(options={"require_reauth": True}, exception_only=False)

        derived_view = manage.reauth_view(view, info)
        result = derived_view(context, dummy_request)

        assert "form" in result
        assert result["form"] == mock_form
        # Since the JSON is invalid, errors shouldn't be set/modified
        assert mock_form.password.errors == []

    @pytest.mark.parametrize(
        ("require_reauth", "needs_reauth_calls"),
        [
            (True, [pretend.call(manage.DEFAULT_TIME_TO_REAUTH)]),
            (666, [pretend.call(666)]),
        ],
    )
    def test_reauth_view_sets_errors(self, monkeypatch, require_reauth, needs_reauth_calls):
        # Step 1: Mock the field that should have errors
        mock_field = pretend.stub(errors=[])

        # Step 2: Mock the form that has the password field
        form = pretend.stub(password=mock_field)

        # Step 3: Ensure that ReAuthenticateForm uses this mocked form
        monkeypatch.setattr(manage, "ReAuthenticateForm", lambda *a, **kw: form)

        # Step 4: Mock the render_to_response function (doesn't matter for this test)
        monkeypatch.setattr(manage, "render_to_response", lambda *a, **kw: {})

        # Step 5: Define the request and the parameters that simulate the test case
        request = pretend.stub(
            session=pretend.stub(needs_reauthentication=lambda *a: True),
            params={"errors": json.dumps({"password": ["Invalid password"]})},  # mock errors
            POST={},
            GET=pretend.stub(mixed=lambda: {}),
            matched_route=pretend.stub(name="reauth"),
            matchdict={},
            user=pretend.stub(username="tester"),
            find_service=lambda *a, **kw: pretend.stub(),
        )

        context = pretend.stub()
        info = pretend.stub(options={"require_reauth": True})
        view = lambda context, request: None  # Mock view function

        # Step 6: Wrap the view with the reauth_view
        wrapped = manage.reauth_view(view, info)

        # Step 7: Call the wrapped view
        wrapped(context, request)

        # Step 8: Confirm that the field.errors were set correctly
        assert mock_field.errors == ["Invalid password"], f"Expected errors to be ['Invalid password'], but got {mock_field.errors}"


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
