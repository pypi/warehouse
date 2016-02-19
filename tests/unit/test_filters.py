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

import urllib.parse

import jinja2
import pretend
import pytest
import readme_renderer.rst

from warehouse import filters


def test_camo_url():
    c_url = filters._camo_url(
        "https://camo.example.net/",
        "fake key",
        "http://example.com/image.jpg",
    )
    assert c_url == (
        "https://camo.example.net/b410d235a3d2fc44b50ccab827e531dece213062/"
        "687474703a2f2f6578616d706c652e636f6d2f696d6167652e6a7067"
    )


class TestReadmeRender:

    def test_can_render(self, monkeypatch):
        monkeypatch.setattr(
            readme_renderer.rst,
            "render",
            lambda raw: "rendered",
        )

        ctx = {
            "request": pretend.stub(
                registry=pretend.stub(
                    settings={
                        "camo.url": "https://camo.example.net/",
                        "camo.key": "fake key",
                    },
                ),
            ),
        }

        result = filters.readme(ctx, "raw thing", format="rst")

        assert result == jinja2.Markup("rendered")

    def test_cant_render(self, monkeypatch):
        monkeypatch.setattr(readme_renderer.rst, "render", lambda raw: None)
        monkeypatch.setattr(
            readme_renderer.txt, "render", lambda raw: "rendered<br>thing",
        )

        ctx = {
            "request": pretend.stub(
                registry=pretend.stub(
                    settings={
                        "camo.url": "https://camo.example.net/",
                        "camo.key": "fake key",
                    },
                ),
            ),
        }

        result = filters.readme(ctx, "raw thing", format="rst")

        assert result == jinja2.Markup("rendered<br>thing")

    def test_renders_camo(self, monkeypatch):
        html = "<img src=http://example.com/image.jpg>"
        monkeypatch.setattr(readme_renderer.rst, "render", lambda raw: html)

        gen_camo_url = pretend.call_recorder(
            lambda curl, ckey, url: "https://camo.example.net/image.jpg"
        )
        monkeypatch.setattr(filters, "_camo_url", gen_camo_url)

        ctx = {
            "request": pretend.stub(
                registry=pretend.stub(
                    settings={
                        "camo.url": "https://camo.example.net/",
                        "camo.key": "fake key",
                    },
                ),
            ),
        }

        result = filters.readme(ctx, "raw thing", format="rst")

        assert result == jinja2.Markup(
            "<img src=https://camo.example.net/image.jpg>"
        )
        assert gen_camo_url.calls == [
            pretend.call(
                "https://camo.example.net/",
                "fake key",
                "http://example.com/image.jpg",
            ),
        ]

    def test_renders_camo_no_src(self, monkeypatch):
        html = "<img>"
        monkeypatch.setattr(readme_renderer.rst, "render", lambda raw: html)

        gen_camo_url = pretend.call_recorder(
            lambda curl, ckey, url: "https://camo.example.net/image.jpg"
        )
        monkeypatch.setattr(filters, "_camo_url", gen_camo_url)

        ctx = {
            "request": pretend.stub(
                registry=pretend.stub(
                    settings={
                        "camo.url": "https://camo.example.net/",
                        "camo.key": "fake key",
                    },
                ),
            ),
        }

        result = filters.readme(ctx, "raw thing", format="rst")

        assert result == jinja2.Markup("<img>")
        assert gen_camo_url.calls == []


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (1, "1"),
        (999, "999"),
        (1234, "1.23k"),
        (4304264, "4.3M"),
        (7878123132, "7.88G"),
        (9999999999999, "10T"),
    ],
)
def test_shorten_number(inp, expected):
    assert filters.shorten_number(inp) == expected


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        ({"foo": "bar", "left": "right"}, '{"foo":"bar","left":"right"}'),
    ],
)
def test_tojson(inp, expected):
    assert filters.tojson(inp) == expected


def test_urlparse():
    inp = "https://google.com/foo/bar?a=b"
    expected = urllib.parse.urlparse(inp)
    assert filters.urlparse(inp) == expected


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (
            "'python', finance, \"data\",        code    , test automation",
            ["python", "finance", "data", "code", "test automation"]
        ),
        (
            "'python'; finance; \"data\";        code    ; test automation",
            ["python", "finance", "data", "code", "test automation"]
        ),
        (
            "a \"b\" c   d  'e'",
            ["a", "b", "c", "d", "e"]
        ),
        (
            "      '    '   \"  \"",
            []
        )
    ]
)
def test_format_tags(inp, expected):
    assert filters.format_tags(inp) == expected
