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
import six

from warehouse.utils import (
    AttributeDict, FastlyFormatter, convert_to_attr_dict, merge_dict,
    render_response, cache, get_wsgi_application, get_mimetype, redirect,
    SearchPagination, is_valid_json_callback_name, generate_camouflage_url,
    camouflage_images,
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
            gravatar_url=mock.ANY,
            url_for=mock.ANY,
            static_url=mock.ANY,
        ),
    ]


@pytest.mark.parametrize(
    ("browser", "varnish", "status"),
    [
        (None, None, 200),
        (1, None, 200),
        (None, 120, 200),
        (1, 120, 200),
        (None, None, 400),
        (1, None, 400),
        (None, 120, 400),
        (1, 120, 400),
    ],
)
def test_cache_deco(browser, varnish, status):
    response = pretend.stub(
        status_code=status,
        cache_control=pretend.stub(),
        surrogate_control=pretend.stub(),
    )
    view = pretend.call_recorder(lambda *a, **kw: response)

    app = pretend.stub()
    request = pretend.stub()

    resp = cache(browser=browser, varnish=varnish)(view)(app, request)

    assert resp is response

    if 200 <= resp.status_code < 400:
        if browser:
            assert resp.cache_control.public
            assert resp.cache_control.max_age == browser

        if varnish:
            assert resp.surrogate_control.public
            assert resp.surrogate_control.max_age == varnish


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


def test_redirect_bytes():
    resp = redirect(b"/foo/")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/foo/"


def test_redirect_unicode():
    resp = redirect(six.text_type("/foo/"))
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/foo/"


def test_fastly_formatter():
    assert FastlyFormatter().format("{0}", "Foo") == "Foo"
    assert FastlyFormatter().format("{0!n}", "Foo") == "foo"


class TestSearchPagination:

    def test_pages(self):
        paginator = SearchPagination(total=100, per_page=10, url=None, page=1)
        assert paginator.pages == 10

    @pytest.mark.parametrize(("total", "per_page", "page", "has"), [
        (100, 10, 1, False),
        (100, 10, 2, True),
    ])
    def test_has_prev(self, total, per_page, page, has):
        paginator = SearchPagination(
            total=total,
            per_page=per_page,
            url=None,
            page=page,
        )
        assert paginator.has_prev == has

    @pytest.mark.parametrize(("total", "per_page", "page", "has"), [
        (100, 10, 10, False),
        (100, 10, 9, True),
    ])
    def test_has_next(self, total, per_page, page, has):
        paginator = SearchPagination(
            total=total,
            per_page=per_page,
            url=None,
            page=page,
        )
        assert paginator.has_next == has

    def test_prev_url(self):
        prev_url = pretend.stub()
        url = pretend.call_recorder(lambda **kw: prev_url)
        paginator = SearchPagination(total=100, per_page=10, url=url, page=2)

        assert paginator.prev_url is prev_url
        assert url.calls == [pretend.call(page=1)]

    def test_next_url(self):
        next_url = pretend.stub()
        url = pretend.call_recorder(lambda **kw: next_url)
        paginator = SearchPagination(total=100, per_page=10, url=url, page=1)

        assert paginator.next_url is next_url
        assert url.calls == [pretend.call(page=2)]


@pytest.mark.parametrize(("callback", "expected"), [
    ("", False),
    ("too long" * 50, False),
    ("somehack()", False),
    ("break", False),
    ("valid", True),
])
def test_is_valid_json_callback_name(callback, expected):
    assert is_valid_json_callback_name(callback) == expected


@pytest.mark.parametrize(("camo_url", "camo_key", "url", "expected"), [
    (
        "https://camo.example.com/",
        "123",
        "https://example.com/fake.png",
        "https://camo.example.com/dec25c03d21dc84f233f39c6107d305120746ca0/"
        "68747470733a2f2f6578616d706c652e636f6d2f66616b652e706e67",
    )
])
def test_generate_camouflage_url(camo_url, camo_key, url, expected):
    assert generate_camouflage_url(camo_url, camo_key, url) == expected


@pytest.mark.parametrize(("camo_url", "camo_key", "html", "expected"), [
    (
        "https://camo.example.com/",
        "123",
        '<html><body><img src="http://example.com/fake.png"></body></html>',
        '<img src=https://camo.example.com/d59e450f25b4dad6ef4bc4bd71fef1f10d1'
        '74273/687474703a2f2f6578616d706c652e636f6d2f66616b652e706e67>',
    ),
    (
        "https://camo.example.com/",
        "123",
        '<html><body><img alt="whatever"></body></html>',
        "<img alt=whatever>",
    ),
])
def test_camouflage_images(camo_url, camo_key, html, expected):
    assert camouflage_images(camo_url, camo_key, html) == expected
