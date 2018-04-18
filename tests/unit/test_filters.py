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

from functools import partial

import packaging.version
import pretend
import pytest

from warehouse import filters


def test_camo_url():
    request = pretend.stub(
        registry=pretend.stub(
            settings={
                "camo.url": "https://camo.example.net/",
                "camo.key": "fake key",
            },
        ),
    )
    c_url = filters._camo_url(
        request,
        "http://example.com/image.jpg",
    )
    assert c_url == (
        "https://camo.example.net/b410d235a3d2fc44b50ccab827e531dece213062/"
        "687474703a2f2f6578616d706c652e636f6d2f696d6167652e6a7067"
    )


class TestCamoify:
    def test_camoify(self):
        html = "<img src=http://example.com/image.jpg>"

        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "camo.url": "https://camo.example.net/",
                    "camo.key": "fake key",
                },
            ),
        )
        camo_url = partial(filters._camo_url, request)
        request.camo_url = camo_url

        ctx = {"request": request}

        result = filters.camoify(
            ctx, html
        )

        assert result == (
            '<img src="https://camo.example.net/'
            'b410d235a3d2fc44b50ccab827e531dece213062/'
            '687474703a2f2f6578616d706c652e636f6d2f696d6167652e6a7067">')

    def test_camoify_no_src(self, monkeypatch):
        html = "<img>"

        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "camo.url": "https://camo.example.net/",
                    "camo.key": "fake key",
                },
            ),
        )
        camo_url = partial(filters._camo_url, request)
        request.camo_url = camo_url

        ctx = {"request": request}

        gen_camo_url = pretend.call_recorder(
            lambda curl, ckey, url: "https://camo.example.net/image.jpg"
        )
        monkeypatch.setattr(filters, "_camo_url", gen_camo_url)

        result = filters.camoify(ctx, html)

        assert result == "<img>"
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


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (
            ["Foo :: Bar :: Baz", "Foo :: Bar :: Qux", "Vleep"],
            [("Foo", ["Bar :: Baz", "Bar :: Qux"])],
        ),
        (
            ["Vleep :: Foo", "Foo :: Bar :: Qux", "Foo :: Bar :: Baz"],
            [("Foo", ["Bar :: Baz", "Bar :: Qux"]), ("Vleep", ["Foo"])],
        ),
    ],
)
def test_format_classifiers(inp, expected):
    assert list(filters.format_classifiers(inp).items()) == expected


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (
            ["abcdef", "ghijkl"],
            False
        ),
        (
            ["https://github.com/example/test", "https://pypi.io/"],
            True
        ),
        (
            ["abcdef", "https://github.com/example/test"],
            True
        )
    ]
)
def test_contains_valid_uris(inp, expected):
    assert filters.contains_valid_uris(inp) == expected


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        ("bdist_dmg", "OSX Disk Image"),
        ("bdist_dumb", "Dumb Binary"),
        ("bdist_egg", "Egg"),
        ("bdist_msi", "Windows MSI Installer"),
        ("bdist_rpm", "RPM"),
        ("bdist_wheel", "Wheel"),
        ("bdist_wininst", "Windows Installer"),
        ("sdist", "Source"),
        ("invalid", "invalid"),
    ],
)
def test_format_package_type(inp, expected):
    assert filters.format_package_type(inp) == expected


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        ("1.0", packaging.version.Version("1.0")),
    ]
)
def test_parse_version(inp, expected):
    assert filters.parse_version(inp) == expected
