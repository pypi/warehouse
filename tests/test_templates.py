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

import collections

from unittest import mock

import pretend
import pytest

from werkzeug.test import create_environ

from warehouse.templates import (
    TemplateRenderer, TemplateResponse, render_response,
)


@pytest.mark.parametrize(("default"), [None, {"foo": pretend.stub()}])
def test_template_renderer(default):
    expected = pretend.stub()
    template = pretend.stub(
        render=pretend.call_recorder(lambda **kw: expected)
    )
    ctx = {
        "wat": pretend.stub(),
    }

    renderer = TemplateRenderer(template, ctx, default_context=default)

    assert renderer.template is template
    assert renderer.context == ctx
    assert renderer.default_context == (default or {})
    assert not renderer.rendered

    assert isinstance(renderer, collections.Iterator)

    rendered = next(renderer)

    assert rendered is expected
    assert renderer.rendered

    with pytest.raises(StopIteration):
        next(renderer)


def test_template_response_repr():
    template = pretend.stub(render=lambda **kw: b"watwat")
    ctx = {"wat": pretend.stub()}

    renderer = TemplateRenderer(template, ctx)

    response = TemplateResponse(renderer)

    assert repr(response) == "<TemplateResponse 6 bytes [200 OK]>"


def test_template_response_get_wsgi_headers():
    template = pretend.stub(render=lambda **kw: b"watwat")
    ctx = {"wat": pretend.stub()}

    renderer = TemplateRenderer(template, ctx)
    response = TemplateResponse(renderer)

    assert dict(response.get_wsgi_headers(create_environ())) == {
        "Content-Type": "text/plain; charset=utf-8",
        "Content-Length": "6",
    }


def test_template_response_is_streaming():
    response = TemplateResponse(iter([]))
    assert not response.is_streamed


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

    assert resp.get_wsgi_headers(create_environ())["Content-Length"] == "4"
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
