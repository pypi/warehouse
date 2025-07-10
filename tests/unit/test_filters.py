# SPDX-License-Identifier: Apache-2.0

import datetime

from functools import partial

import packaging.version
import packaging_legacy.version
import pretend
import pytest

from urllib3.util import parse_url

from warehouse import filters
from warehouse.utils import now


def test_now():
    assert isinstance(now(), datetime.datetime)
    assert now().tzinfo is None
    with pytest.raises(TypeError) as excinfo:
        _ = now() < datetime.datetime.now(datetime.UTC)
    assert "can't compare offset-naive and offset-aware datetimes" in str(excinfo.value)
    assert now() <= datetime.datetime.now()


def test_camo_url():
    request = pretend.stub(
        registry=pretend.stub(
            settings={"camo.url": "https://camo.example.net/", "camo.key": "fake key"}
        )
    )
    c_url = filters._camo_url(request, "http://example.com/image.jpg")
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
                }
            )
        )
        camo_url = partial(filters._camo_url, request)
        request.camo_url = camo_url

        ctx = {"request": request}

        result = filters.camoify(ctx, html)

        assert result == (
            '<img src="https://camo.example.net/'
            "b410d235a3d2fc44b50ccab827e531dece213062/"
            '687474703a2f2f6578616d706c652e636f6d2f696d6167652e6a7067">'
        )

    def test_camoify_no_src(self, monkeypatch):
        html = "<img>"

        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "camo.url": "https://camo.example.net/",
                    "camo.key": "fake key",
                }
            )
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
    [({"foo": "bar", "left": "right"}, '{"foo":"bar","left":"right"}')],
)
def test_tojson(inp, expected):
    assert filters.tojson(inp) == expected


def test_urlparse():
    inp = "https://google.com/foo/bar?a=b"
    expected = parse_url(inp)
    assert filters.urlparse(inp) == expected


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (
            "'python', finance, \"data\",        code    , test automation",
            ["python", "finance", "data", "code", "test automation"],
        ),
        (
            "'python'; finance; \"data\";        code    ; test automation",
            ["python", "finance", "data", "code", "test automation"],
        ),
        ("a \"b\" c   d  'e'", ["a", "b", "c", "d", "e"]),
        ("      '    '   \"  \"", []),
    ],
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
            ["Foo :: Bar :: Baz", "Vleep :: Foo", "Foo :: Bar :: Qux"],
            [("Foo", ["Bar :: Baz", "Bar :: Qux"]), ("Vleep", ["Foo"])],
        ),
        (
            [
                "Programming Language :: Python :: 3.11",
                "Programming Language :: Python :: 3.10",
                "Programming Language :: Python :: 3.8",
            ],
            [
                (
                    "Programming Language",
                    ["Python :: 3.8", "Python :: 3.10", "Python :: 3.11"],
                )
            ],
        ),
    ],
)
def test_format_classifiers(inp, expected):
    assert list(filters.format_classifiers(inp).items()) == expected


@pytest.mark.parametrize(
    ("inp", "expected"), [("Foo", "Foo"), ("Foo :: Foo", "Foo_._Foo")]
)
def test_classifier_id(inp, expected):
    assert filters.classifier_id(inp) == expected


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (["abcdef", "ghijkl"], False),
        (["https://github.com/example/test", "https://pypi.io/"], True),
        (["abcdef", "https://github.com/example/test"], True),
    ],
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
        ("dog", packaging_legacy.version.LegacyVersion("dog")),
    ],
)
def test_parse_version(inp, expected):
    assert filters.parse_version(inp) == expected


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (
            datetime.datetime(2018, 12, 26, 13, 36, 5, 789013),
            "2018-12-26 13:36:05.789013 UTC",
        )
    ],
)
def test_localize_datetime(inp, expected):
    datetime_format = "%Y-%m-%d %H:%M:%S.%f %Z"
    assert filters.localize_datetime(inp).strftime(datetime_format) == expected


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (
            datetime.datetime(2018, 12, 26, 13, 36, 5, 789013).isoformat(),
            datetime.datetime(2018, 12, 26, 13, 36, 5, 789013),
        )
    ],
)
def test_parse_isoformat(inp, expected):
    assert filters.parse_isoformat(inp) == expected


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (
            1667404296,
            datetime.datetime(2022, 11, 2, 15, 51, 36),
        )
    ],
)
def test_ctime(inp, expected):
    assert filters.ctime(inp) == expected


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (datetime.timedelta(days=31), False),
        (datetime.timedelta(days=30), False),
        (datetime.timedelta(days=29), True),
        (datetime.timedelta(), True),
        (datetime.timedelta(days=-1), True),
    ],
)
def test_is_recent(delta, expected):
    timestamp = datetime.datetime.now() - delta
    assert filters.is_recent(timestamp) == expected


def test_is_recent_none():
    assert filters.is_recent(None) is False


@pytest.mark.parametrize(
    ("meta_email", "expected_name", "expected_email"),
    [
        ("not-an-email-address", "", ""),
        ("foo@bar.com", "", "foo@bar.com"),
        ('"Foo Bar" <foo@bar.com>', "Foo Bar", "foo@bar.com"),
    ],
)
def test_format_email(meta_email, expected_name, expected_email):
    name, email = filters.format_email(meta_email)
    assert name == expected_name
    assert email == expected_email


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        ("foo", "foo"),  # no change
        (" foo  bar ", " foo  bar "),  # U+001B : <control> ESCAPE [ESC]
        ("foo \x1b bar", "foo  bar"),  # U+001B : <control> ESCAPE [ESC]
        ("foo \x00 bar", "foo  bar"),  # U+0000 : <control> NULL
        ("foo 🐍 bar", "foo 🐍 bar"),  # U+1F40D : SNAKE [snake] (emoji) [Python]
        (None, None),  # no change
    ],
)
def test_remove_invalid_xml_unicode(inp, expected):
    """
    Test that invalid XML unicode characters are removed.
    """
    assert filters.remove_invalid_xml_unicode(inp) == expected


def test_canonical_url():
    request = pretend.stub(
        matched_route=pretend.stub(name="foo"),
        route_url=pretend.call_recorder(lambda a: "bar"),
    )
    assert filters._canonical_url(request) == "bar"
    assert request.route_url.calls == [pretend.call("foo")]


def test_canonical_url_no_matched_route():
    request = pretend.stub(matched_route=None)
    assert filters._canonical_url(request) is None


def test_canonical_url_missing_kwargs():
    request = pretend.stub(
        matched_route=pretend.stub(name="foo"),
        route_url=pretend.raiser(KeyError),
    )
    assert filters._canonical_url(request) is None
