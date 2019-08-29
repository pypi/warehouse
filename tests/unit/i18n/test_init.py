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
    locale_cls = pretend.stub(parse=pretend.call_recorder(lambda l: locale_obj))
    monkeypatch.setattr(i18n, "Locale", locale_cls)
    request = pretend.stub(locale_name=pretend.stub())

    assert i18n._locale(request) is locale_obj
    assert locale_cls.parse.calls == [pretend.call(request.locale_name)]


def test_includeme():
    config_settings = {}
    config = pretend.stub(
        add_translation_dirs=pretend.call_recorder(lambda s: None),
        set_locale_negotiator=pretend.call_recorder(lambda f: None),
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        get_settings=lambda: config_settings,
    )

    i18n.includeme(config)

    assert config.add_translation_dirs.calls == [
        pretend.call("warehouse:locale/")
    ]
    assert config.set_locale_negotiator.calls == [
        pretend.call(i18n._negotiate_locale)
    ]
    assert config.add_request_method.calls == [
        pretend.call(i18n._locale, name="locale", reify=True)
    ]
    assert config_settings == {
        "jinja2.filters": {
            "format_date": "warehouse.i18n.filters:format_date",
            "format_datetime": "warehouse.i18n.filters:format_datetime",
            "format_rfc822_datetime": "warehouse.i18n.filters:format_rfc822_datetime",
            "format_number": "warehouse.i18n.filters:format_number",
        }
    }
