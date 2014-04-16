# Copyright 2014 Donald Stufft
#
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

from unittest import mock

import pretend

from warehouse.templates import TemplateResponse, render_response


def test_template_response():
    response = pretend.stub()
    template = pretend.stub(
        render=pretend.call_recorder(lambda **kw: response)
    )
    ctx = {
        "wat": pretend.stub(),
    }
    default_ctx = {
        "foo": pretend.stub(),
    }
    resp = TemplateResponse(template, ctx, default_context=default_ctx)

    assert resp.template is template
    assert resp.context == ctx
    assert resp.default_context == default_ctx

    assert resp.response is response

    assert resp.template is None
    assert resp.context is None
    assert resp.default_context is None


def test_render_response():
    template = pretend.stub(render=pretend.call_recorder(lambda **k: "test"))
    app = pretend.stub(
        config=pretend.stub(),
        templates=pretend.stub(
            get_template=pretend.call_recorder(lambda t: template),
        ),
    )
    request = pretend.stub()

    resp = render_response(app, request, "template.html", foo="bar")

    assert resp.data == b"test"
    assert app.templates.get_template.calls == [pretend.call("template.html")]
    assert template.render.calls == [
        pretend.call(
            foo="bar",
            config=app.config,
            csrf_token=mock.ANY,
            gravatar_url=mock.ANY,
            url_for=mock.ANY,
            static_url=mock.ANY,
        ),
    ]
