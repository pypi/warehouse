# SPDX-License-Identifier: Apache-2.0

import types

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
    def test_invalid_localizer(self, mocker, pyramid_request, has_translations):
        def _view(context, request):
            assert isinstance(request.localizer, i18n.InvalidLocalizer)
            return mocker.sentinel.response

        view = mocker.Mock(side_effect=_view)

        # A pre-existing localizer exercises the restore (not the delete) branch
        # of the wrapper's finally clause.
        pyramid_request.localizer = mocker.sentinel.original_localizer

        info = types.SimpleNamespace(options={}, exception_only=False)
        if has_translations is not None:
            info.options["has_translations"] = has_translations
        derived_view = i18n.translated_view(view, info)

        assert (
            derived_view(mocker.sentinel.context, pyramid_request)
            is mocker.sentinel.response
        )
        view.assert_called_once_with(mocker.sentinel.context, pyramid_request)

    def test_valid_localizer(self, mocker, pyramid_request):
        add_vary_cb = mocker.Mock(side_effect=lambda fn: fn)
        add_vary = mocker.patch.object(
            i18n, "add_vary", autospec=True, return_value=add_vary_cb
        )

        pyramid_request.localizer = Localizer(locale_name="en", translations=[])

        def _view(context, request):
            assert isinstance(request.localizer, Localizer)
            return mocker.sentinel.response

        view = mocker.Mock(side_effect=_view)

        info = types.SimpleNamespace(options={"has_translations": True})
        derived_view = i18n.translated_view(view, info)

        assert (
            derived_view(mocker.sentinel.context, pyramid_request)
            is mocker.sentinel.response
        )
        view.assert_called_once_with(mocker.sentinel.context, pyramid_request)
        add_vary.assert_called_once_with("PyPI-Locale")
        add_vary_cb.assert_called_once_with(view)


def test_sets_locale(mocker, pyramid_request):
    locale_obj = mocker.sentinel.locale_obj
    mocker.patch.object(
        i18n,
        "KNOWN_LOCALES",
        {mocker.sentinel.locale_name: locale_obj, "en": mocker.sentinel.en},
    )
    pyramid_request.locale_name = mocker.sentinel.locale_name

    assert i18n._locale(pyramid_request) is locale_obj


def test_when_locale_is_missing(mocker, pyramid_request):
    locale_obj = mocker.sentinel.locale_obj
    mocker.patch.object(i18n, "KNOWN_LOCALES", {"en": locale_obj})
    pyramid_request.locale_name = None

    assert i18n._locale(pyramid_request) is locale_obj


@pytest.mark.parametrize(
    ("locale_attr", "params", "cookies", "accept_language", "expected"),
    [
        ("eo", None, None, None, "eo"),
        (None, {"_LOCALE_": "eo"}, None, None, "eo"),
        (None, {}, {"_LOCALE_": "eo"}, None, "eo"),
        (None, {}, {}, None, None),
        (None, {}, {}, AcceptLanguageValidHeader(header_value="eo"), "eo"),
        ("garbage", {}, {}, None, None),
        (None, {"_LOCALE_": "garbage"}, {}, None, None),
        (None, {}, {"_LOCALE_": "garbage"}, None, None),
        ("he", None, None, AcceptLanguageValidHeader(header_value="eo"), "he"),
        ("garbage", None, None, AcceptLanguageValidHeader(header_value="xx"), None),
    ],
)
def test_negotiate_locale(
    pyramid_request, locale_attr, params, cookies, accept_language, expected
):
    if locale_attr is not None:
        pyramid_request._LOCALE_ = locale_attr
    if params is not None:
        pyramid_request.params = params
    if cookies is not None:
        pyramid_request.cookies = cookies
    pyramid_request.accept_language = accept_language

    assert i18n._negotiate_locale(pyramid_request) == expected


def test_localize(mocker, pyramid_request):
    localizer = mocker.create_autospec(Localizer, instance=True)
    localizer.translate.return_value = "fake translated string"
    pyramid_request.localizer = localizer
    mocker.patch.object(i18n, "get_current_request", return_value=pyramid_request)

    assert str(i18n.localize("foo")) == "fake translated string"


def test_includeme(mocker):
    config_settings = {}
    config = mocker.Mock(
        spec=[
            "add_translation_dirs",
            "set_locale_negotiator",
            "add_request_method",
            "get_settings",
            "add_view_deriver",
        ]
    )
    config.get_settings.return_value = config_settings

    i18n.includeme(config)

    config.add_translation_dirs.assert_called_once_with("warehouse:locale/")
    config.set_locale_negotiator.assert_called_once_with(i18n._negotiate_locale)
    assert config.add_request_method.call_args_list == [
        mocker.call(i18n._locale, name="locale", reify=True),
        mocker.call(i18n._localize, name="_"),
    ]
    config.add_view_deriver.assert_called_once_with(
        i18n.translated_view, over="rendered_view", under=viewderivers.INGRESS
    )
    assert config_settings == {
        "jinja2.i18n_extension": FallbackInternationalizationExtension,
        "jinja2.filters": {
            "format_date": "warehouse.i18n.filters:format_date",
            "format_datetime": "warehouse.i18n.filters:format_datetime",
            "format_rfc822_datetime": "warehouse.i18n.filters:format_rfc822_datetime",
            "format_number": "warehouse.i18n.filters:format_number",
        },
        "jinja2.globals": {
            "KNOWN_LOCALES": "warehouse.i18n:KNOWN_LOCALES",
        },
    }


def test_lazy_string():
    def stringify(string_in, *args, **kwargs):
        return string_in

    lazy_string = i18n.LazyString(stringify, "test_string")
    equally_lazy_string = i18n.LazyString(stringify, "test_string")

    assert lazy_string.__json__(None) == "test_string"
    assert lazy_string == "test_string"
    assert lazy_string == equally_lazy_string
