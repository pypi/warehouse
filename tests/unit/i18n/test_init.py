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

import pretend
import pytest

from pyramid import viewderivers
from pyramid.i18n import Localizer

from warehouse import i18n


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
    locale_obj = pretend.stub()
    locale_cls = pretend.stub(parse=pretend.call_recorder(lambda l, **kw: locale_obj))
    monkeypatch.setattr(i18n, "Locale", locale_cls)
    request = pretend.stub(locale_name=pretend.stub())

    assert i18n._locale(request) is locale_obj
    assert locale_cls.parse.calls == [pretend.call(request.locale_name, sep="_")]


def test_negotiate_locale(monkeypatch):
    request = pretend.stub(_LOCALE_="fake-locale-attr")
    assert i18n._negotiate_locale(request) == "fake-locale-attr"

    request = pretend.stub(params={"_LOCALE_": "fake-locale-param"})
    assert i18n._negotiate_locale(request) == "fake-locale-param"

    request = pretend.stub(params={}, cookies={"_LOCALE_": "fake-locale-cookie"})
    assert i18n._negotiate_locale(request) == "fake-locale-cookie"

    request = pretend.stub(params={}, cookies={}, accept_language=None)
    default_locale_negotiator = pretend.call_recorder(lambda r: "fake-locale-default")
    monkeypatch.setattr(i18n, "default_locale_negotiator", default_locale_negotiator)
    assert i18n._negotiate_locale(request) == "fake-locale-default"

    request = pretend.stub(
        params={},
        cookies={},
        accept_language=pretend.stub(
            best_match=pretend.call_recorder(lambda *a, **kw: "fake-locale-best-match")
        ),
    )
    assert i18n._negotiate_locale(request) == "fake-locale-best-match"


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
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        get_settings=lambda: config_settings,
        add_view_deriver=pretend.call_recorder(lambda f, over, under: None),
    )

    i18n.includeme(config)

    assert config.add_translation_dirs.calls == [pretend.call("warehouse:locale/")]
    assert config.set_locale_negotiator.calls == [pretend.call(i18n._negotiate_locale)]
    assert config.add_request_method.calls == [
        pretend.call(i18n._locale, name="locale", reify=True)
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
        "jinja2.globals": {"KNOWN_LOCALES": "warehouse.i18n:KNOWN_LOCALES"},
    }


def test_lazy_string():
    def stringify(string_in, *args, **kwargs):
        return string_in

    lazy_string = i18n.LazyString(stringify, "test_string")

    assert lazy_string.__json__(None) == "test_string"
