# Copyright 2013 Donald Stufft
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import mock
import pretend
import pytest

from warehouse.utils import (
    AttributeDict, convert_to_attr_dict, merge_dict, render_response, cache,
    get_wsgi_application, get_mimetype,
)


def test_basic_attribute_dict_access():
    adict = AttributeDict({
        "foo": None,
        "bar": "Success!"
    })

    assert adict.foo is adict["foo"]
    assert adict.bar is adict["bar"]


def test_attribute_dict_unknown_access():
    adict = AttributeDict()

    with pytest.raises(AttributeError):
        adict.unknown


@pytest.mark.parametrize(("base", "additional", "expected"), [
    ({"a": 1}, {"a": 2}, {"a": 2}),
    ({"a": 1}, {"b": 2}, {"a": 1, "b": 2}),
    ({"a": 1, "b": 2}, {"b": 3, "c": 4}, {"a": 1, "b": 3, "c": 4}),
    (None, {"a": 2}, {"a": 2}),
    ({"a": 1}, None, {"a": 1}),
    ("Test", {"a": 7}, {"a": 7}),
    ({"a": 9}, "Test", "Test"),
    ({"a": {"b": 3}}, {"a": {"b": 7, "c": 0}}, {"a": {"b": 7, "c": 0}}),
])
def test_merge_dictionary(base, additional, expected):
    assert merge_dict(base, additional) == expected


def test_convert_to_attribute_dict():
    adict = convert_to_attr_dict({"a": {"b": 1, "c": 2}})

    assert adict.a == {"b": 1, "c": 2}
    assert adict.a.b == 1
    assert adict.a.c == 2


def test_render_response():
    template = pretend.stub(render=pretend.call_recorder(lambda **k: "test"))
    app = pretend.stub(
        templates=pretend.stub(
            get_template=pretend.call_recorder(lambda t: template),
        ),
    )
    request = pretend.stub()

    resp = render_response(app, request, "template.html", foo="bar")

    assert resp.data == b"test"
    assert app.templates.get_template.calls == [pretend.call("template.html")]
    assert template.render.calls == [pretend.call(foo="bar", url_for=mock.ANY)]


@pytest.mark.parametrize(("browser", "varnish"), [
    ({}, {}),
    ({"test": 120}, {}),
    ({}, {"test": 120}),
    ({"test": 120}, {"test": 120}),
])
def test_cache_deco(browser, varnish):
    response = pretend.stub(
        cache_control=pretend.stub(),
        surrogate_control=pretend.stub(),
    )
    view = pretend.call_recorder(lambda *a, **kw: response)

    app = pretend.stub(
        config=pretend.stub(
            cache=pretend.stub(
                browser=browser,
                varnish=varnish,
            ),
        ),
    )
    request = pretend.stub()

    resp = cache("test")(view)(app, request)

    assert resp is response

    if browser:
        assert resp.cache_control.max_age == browser["test"]

    if varnish:
        assert resp.surrogate_control.max_age == varnish["test"]


@pytest.mark.parametrize("environ", [
    {"WAREHOUSE_CONF": "/tmp/config.yml"},
    {},
])
def test_get_wsgi_application(environ):
    obj = pretend.stub()
    klass = pretend.stub(from_yaml=pretend.call_recorder(lambda *a, **k: obj))

    app = get_wsgi_application(environ, klass)
    config = environ.get("WAREHOUSE_CONF")
    configs = [config] if config else []

    assert app is obj
    assert klass.from_yaml.calls == [pretend.call(*configs)]


@pytest.mark.parametrize(("filename", "expected"), [
    ("warehouse-13.10.0.tar.gz", "application/x-tar"),
    ("warehouse-13.10.0-py2.py3-none-any.whl", "application/octet-stream"),
])
def test_get_mimetype(filename, expected):
    assert get_mimetype(filename) == expected
