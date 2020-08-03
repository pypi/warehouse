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

from pyramid import viewderivers

from warehouse import manage


class TestReAuthView:
    def test_has_options(self):
        assert set(manage.reauth_view.options) == {"require_reauth"}

    @pytest.mark.parametrize("requires_reauth", [True, False])
    def test_unneeded_reauth(self, requires_reauth):
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
        info.options["require_reauth"] = requires_reauth
        derived_view = manage.reauth_view(view, info)

        assert derived_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]
        assert request.session.needs_reauthentication.calls == (
            [pretend.call()] if requires_reauth else []
        )

    def test_reauth(self, monkeypatch):
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
        info.options["require_reauth"] = True
        derived_view = manage.reauth_view(view, info)

        assert derived_view(context, request) is not response
        assert view.calls == []
        assert request.session.needs_reauthentication.calls == [pretend.call()]


def test_includeme():
    config = pretend.stub(
        add_view_deriver=pretend.call_recorder(lambda f, over, under: None),
    )

    manage.includeme(config)

    assert config.add_view_deriver.calls == [
        pretend.call(
            manage.reauth_view, over="rendered_view", under=viewderivers.INGRESS
        )
    ]
