# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from pyramid import viewderivers
from pyramid.i18n import Localizer
from webob.acceptparse import AcceptLanguageValidHeader

from warehouse import i18n
from warehouse.i18n.extensions import FallbackInternationalizationExtension


class TestInvalidLocalizer:
    @pytest.mark.parametrize(
        "method",
        [
            # Our custom methods.
            "pluralize",
            "translate",
        ],
    )
    def test_methods_raise(self, method):
        localizer = i18n.InvalidLocalizer()
        with pytest.raises(RuntimeError):
            getattr(localizer, method)()

    @pytest.mark.parametrize("name", ["locale_name"])
    def test_propery_raises(self, name):
        localizer = i18n.InvalidLocalizer()
        with pytest.raises(RuntimeError):
            getattr(localizer, name)


class TestTranslatedView:
    def test_has_options(self):
        assert set(i18n.translated_view.options) == {"has_translations"}

    @pytest.mark.parametrize("has_translations", [False, None])
    def test_invalid_localizer(self, has_translations):
        context = pretend.stub()
        request = pretend.stub(localizer=pretend.stub())
        response = pretend.stub()

        @pretend.call_recorder
        def view(context, request):
            assert isinstance(request.localizer, i18n.InvalidLocalizer)
            return response

        info = pretend.stub(options={}, exception_only=False)
        if has_translations is not None:
            info.options["has_translations"] = has_translations
        derived_view = i18n.translated_view(view, info)

        assert derived_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]

    def test_valid_localizer(self, monkeypatch):
        add_vary_cb = pretend.call_recorder(lambda fn: fn)
        add_vary = pretend.call_recorder(lambda vary: add_vary_cb)
        monkeypatch.setattr(i18n, "add_vary", add_vary)

        context = pretend.stub()
        request = pretend.stub(localizer=Localizer(locale_name="en", translations=[]))
        response = pretend.stub()

        @pretend.call_recorder
        def view(context, request):
            assert isinstance(request.localizer, Localizer)
            return response

        info = pretend.stub(options={"has_translations": True})
        derived_view = i18n.translated_view(view, info)

        assert derived_view(context, request) is response
        assert view.calls == [pretend.call(context, request)]
        assert add_vary.calls == [pretend.call("PyPI-Locale")]
        assert add_vary_cb.calls == [pretend.call(view)]


def test_sets_locale(monkeypatch):
    locale_name = pretend.stub()
    locale_obj = pretend.stub()
    monkeypatch.setattr(
        i18n, "KNOWN_LOCALES", {locale_name: locale_obj, "en": pretend.stub()}
    )
    request = pretend.stub(locale_name=locale_name)

    assert i18n._locale(request) is locale_obj


def test_when_locale_is_missing(monkeypatch):
    locale_obj = pretend.stub()
    monkeypatch.setattr(i18n, "KNOWN_LOCALES", {"en": locale_obj})
    request = pretend.stub(locale_name=None)

    assert i18n._locale(request) is locale_obj


@pytest.mark.parametrize(
    ("req", "expected"),
    [
        (pretend.stub(_LOCALE_="eo", accept_language=None), "eo"),
        (pretend.stub(params={"_LOCALE_": "eo"}, accept_language=None), "eo"),
        (
            pretend.stub(params={}, cookies={"_LOCALE_": "eo"}, accept_language=None),
            "eo",
        ),
        (pretend.stub(params={}, cookies={}, accept_language=None), None),
        (
            pretend.stub(
                params={},
                cookies={},
                accept_language=AcceptLanguageValidHeader(header_value="eo"),
            ),
            "eo",
        ),
        (
            pretend.stub(
                params={}, cookies={}, _LOCALE_="garbage", accept_language=None
            ),
            None,
        ),
        (
            pretend.stub(
                params={"_LOCALE_": "garbage"}, cookies={}, accept_language=None
            ),
            None,
        ),
        (
            pretend.stub(
                params={}, cookies={"_LOCALE_": "garbage"}, accept_language=None
            ),
            None,
        ),
        (
            pretend.stub(
                _LOCALE_="he",
                accept_language=AcceptLanguageValidHeader(header_value="eo"),
            ),
            "he",
        ),
        (
            pretend.stub(
                _LOCALE_="garbage",
                accept_language=AcceptLanguageValidHeader(header_value="xx"),
            ),
            None,
        ),
    ],
)
def test_negotiate_locale(monkeypatch, req, expected):
    assert i18n._negotiate_locale(req) == expected


def test_localize(monkeypatch):
    request = pretend.stub(
        localizer=pretend.stub(
            translate=pretend.call_recorder(lambda ts: "fake translated string")
        )
    )
    get_current_request = pretend.call_recorder(lambda: request)
    monkeypatch.setattr(i18n, "get_current_request", get_current_request)

    assert str(i18n.localize("foo")) == "fake translated string"


def test_includeme():
    config_settings = {}
    config = pretend.stub(
        add_translation_dirs=pretend.call_recorder(lambda s: None),
        set_locale_negotiator=pretend.call_recorder(lambda f: None),
        add_request_method=pretend.call_recorder(lambda f, name, reify=False: None),
        get_settings=lambda: config_settings,
        add_view_deriver=pretend.call_recorder(lambda f, over, under: None),
    )

    i18n.includeme(config)

    assert config.add_translation_dirs.calls == [pretend.call("warehouse:locale/")]
    assert config.set_locale_negotiator.calls == [pretend.call(i18n._negotiate_locale)]
    assert config.add_request_method.calls == [
        pretend.call(i18n._locale, name="locale", reify=True),
        pretend.call(i18n._localize, name="_"),
    ]
    assert config.add_view_deriver.calls == [
        pretend.call(
            i18n.translated_view, over="rendered_view", under=viewderivers.INGRESS
        )
    ]
    assert config_settings == {
        "jinja2.filters": {
            "format_date": "warehouse.i18n.filters:format_date",
            "format_datetime": "warehouse.i18n.filters:format_datetime",
            "format_rfc822_datetime": "warehouse.i18n.filters:format_rfc822_datetime",
            "format_number": "warehouse.i18n.filters:format_number",
        },
        "jinja2.globals": {
            "KNOWN_LOCALES": "warehouse.i18n:KNOWN_LOCALES",
        },
        "jinja2.i18n_extension": FallbackInternationalizationExtension,
    }


def test_lazy_string():
    def stringify(string_in, *args, **kwargs):
        return string_in

    lazy_string = i18n.LazyString(stringify, "test_string")
    equally_lazy_string = i18n.LazyString(stringify, "test_string")

    assert lazy_string.__json__(None) == "test_string"
    assert lazy_string == "test_string"
    assert lazy_string == equally_lazy_string
