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

from unittest import mock

import pretend
import pytest
import six

from warehouse.http import Response
from warehouse.utils import (
    merge_dict, render_response, cache, get_wsgi_application, get_mimetype,
    redirect, SearchPagination, is_valid_json_callback_name,
    generate_camouflage_url, camouflage_images, cors, redirect_next, vary_by,
    random_token, is_safe_url, find_links_from_html, validate_and_normalize_package_name
)


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


@pytest.mark.parametrize(("values", "host", "kwargs", "expected"), [
    ({}, "example.com", {}, {"location": "/", "code": 303}),
    ({}, "example.com", {"code": 302}, {"location": "/", "code": 302}),
    (
        {},
        "example.com",
        {"default": "/wat/"},
        {"location": "/wat/", "code": 303},
    ),
    (
        {"next": "/wat/"},
        "example.com",
        {},
        {"location": "/wat/", "code": 303},
    ),
    (
        {"next": "/wat/"},
        "example.com",
        {"field_name": "not_next"},
        {"location": "/", "code": 303},
    ),
    (
        {"not_next": "/wat/"},
        "example.com",
        {"field_name": "not_next"},
        {"location": "/wat/", "code": 303},
    ),
    (
        {"next": "http://attacker.com/wat/"},
        "example.com",
        {},
        {"location": "/", "code": 303},
    ),
    (
        {"next": "https://example.com/wat/"},
        "example.com",
        {},
        {"location": "https://example.com/wat/", "code": 303},
    ),
    (
        {"next": "http://example.com/wat/"},
        "example.com",
        {},
        {"location": "http://example.com/wat/", "code": 303},
    ),
])
def test_redirect_next(values, host, kwargs, expected):
    request = pretend.stub(values=values, host=host)
    response = redirect_next(request, **kwargs)

    assert response.headers["Location"] == expected["location"]
    assert response.status_code == expected["code"]


class TestSearchPagination:

    def test_pages(self):
        paginator = SearchPagination(total=100, per_page=10, url=None, page=1)
        assert paginator.pages == 10

    @pytest.mark.parametrize(("total", "per_page", "page", "has"), [
        (100, 10, 1, False),
        (100, 10, 2, True),
        (0, 10, 1, False),
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
        (0, 10, 1, False),
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


def test_cors():
    app = pretend.stub()
    request = pretend.stub()
    response = pretend.stub(headers={})

    resp = cors(lambda *a, **kw: response)(app, request)

    assert resp is response
    assert resp.headers == {"Access-Control-Allow-Origin": "*"}


@pytest.mark.parametrize(("varies", "expected"), [
    ([["Cookie"]], {"cookie"}),
    ([["Cookie"], ["Cookie"]], {"cookie"}),
    ([["Cookie", "Accept-Encoding"]], {"accept-encoding", "cookie"}),
    ([["Cookie"], ["Accept-Encoding"]], {"accept-encoding", "cookie"}),
    (
        [["Cookie", "Accept-Encoding"], ["Cookie"]],
        {"accept-encoding", "cookie"},
    ),
])
def test_vary_by(varies, expected):
    view = lambda app, request: Response("")

    for vary in varies:
        view = vary_by(*vary)(view)

    assert view(pretend.stub(), pretend.stub()).vary.as_set() == expected


def test_random_token():
    random_data = (
        b"\xc3_.S\x17u\xa0_b\xa8P\xd9\xe0|j\xe0#\xb9\x9f\xef\x11\xdb\xdf\xf6"
        b"\xa1\xd9[R\xd6\xde'\xef"
    )
    urandom = pretend.call_recorder(lambda size: random_data)

    assert (random_token(_urandom=urandom)
            == "w18uUxd1oF9iqFDZ4Hxq4CO5n-8R29_2odlbUtbeJ-8")
    assert urandom.calls == [pretend.call(32)]


@pytest.mark.parametrize(("url", "host", "expected"), (
    ("", "example.com", False),
    ("/wat/", "example.com", True),
    ("http://example.com/wat/", "example.com", True),
    ("https://example.com/wat/", "example.com", True),
    ("ftp://example.com/wat/", "example.com", False),
    ("http://attacker.com/wat/", "example.com", False),
    ("https://attacker.com/wat/", "example.com", False),
))
def test_is_safe_url(url, host, expected):
    assert is_safe_url(url, host) is expected


@pytest.mark.parametrize(("html", "expected"), (
    ("<a href='foo'>footext</a><div><a href='bar'>bartext</a><div>", ["foo", "bar"]),
))
def test_find_links_from_html(html, expected):
    assert find_links_from_html(html) == expected


@pytest.mark.parametrize(("input_string", "expected"), (
    ("imabad-name^^^", ValueError),
    ("CaseInsensitive", "caseinsensitive"),
    ("replace_underscores", "replace-underscores"),
    ("-not-alphanumericstart", ValueError),
    ("not-alphanumericend-", ValueError),
    ("123456789", "123456789"),
    ("hoobs#", ValueError)
))
def test_validate_and_normalize_package_name(input_string, expected):
    if expected is ValueError:
        with pytest.raises(ValueError):
            validate_and_normalize_package_name(input_string)
    else:
        assert validate_and_normalize_package_name(input_string) == expected
