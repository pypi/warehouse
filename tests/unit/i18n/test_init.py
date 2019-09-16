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

from warehouse import i18n


def test_sets_locale(monkeypatch):
    locale_obj = pretend.stub()
    locale_cls = pretend.stub(parse=pretend.call_recorder(lambda l, **kw: locale_obj))
    monkeypatch.setattr(i18n, "Locale", locale_cls)
    request = pretend.stub(locale_name=pretend.stub())

    assert i18n._locale(request) is locale_obj
    assert locale_cls.parse.calls == [pretend.call(request.locale_name, sep="-")]


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
    )

    i18n.includeme(config)

    assert config.add_translation_dirs.calls == [pretend.call("warehouse:locale/")]
    assert config.set_locale_negotiator.calls == [pretend.call(i18n._negotiate_locale)]
    assert config.add_request_method.calls == [
        pretend.call(i18n._locale, name="locale", reify=True)
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
