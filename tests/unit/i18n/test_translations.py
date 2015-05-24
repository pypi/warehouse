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

from warehouse.i18n import translations


class TestTranslationString:

    def test_stores_values(self):
        message_id = pretend.stub()
        plural = pretend.stub()
        n = pretend.stub()

        ts = translations.TranslationString(message_id, plural, n)

        assert ts.message_id is message_id
        assert ts.plural is plural
        assert ts.n is n

    def test_cant_specify_only_plural(self):
        message_id = pretend.stub()
        plural = pretend.stub()

        with pytest.raises(ValueError):
            translations.TranslationString(message_id, plural)

    def test_cant_specify_only_n(self):
        message_id = pretend.stub()
        n = pretend.stub()

        with pytest.raises(ValueError):
            translations.TranslationString(message_id, n=n)

    @pytest.mark.parametrize(
        ("args", "expected"),
        [
            (
                ("A Message",),
                "<TranslationString: message_id={!r}>".format("A Message"),
            ),
            (
                ("A Message", "Messages", 3),
                "<TranslationString: message_id={!r} plural={!r} "
                "n={!r}>".format("A Message", "Messages", 3),
            ),
        ],
    )
    def test_repr(self, args, expected):
        ts = translations.TranslationString(*args)
        assert repr(ts) == expected

    def test_mod_errors_non_mapping(self):
        ts = translations.TranslationString("Name is %(name)s")

        with pytest.raises(TypeError):
            ts % (1,)

    def test_mod_adds_mapping_creates(self):
        ts1 = translations.TranslationString("Name is %(name)s")
        ts2 = ts1 % {"name": "MyName"}
        ts3 = ts2 % {"name": "AnotherName"}

        assert ts1.mapping == {}
        assert ts2.mapping == {"name": "MyName"}
        assert ts3.mapping == {"name": "AnotherName"}

    def test_translate_gettext(self):
        ts = translations.TranslationString("Test %(foo)s")
        ts = ts % {"foo": "bar"}

        translation = pretend.stub(
            gettext=pretend.call_recorder(lambda m: "Translated %(foo)s")
        )

        assert ts.translate(translation) == "Translated bar"
        assert translation.gettext.calls == [pretend.call("Test %(foo)s")]

    def test_translate_ngettext(self):
        ts = translations.TranslationString(
            "Test %(foo)s", "Plural %(foos)s", 1,
        )
        ts = ts % {"foo": "bar"}

        translation = pretend.stub(
            ngettext=pretend.call_recorder(
                lambda m, p, n: "Translated %(foo)s"
            ),
        )

        assert ts.translate(translation) == "Translated bar"
        assert translation.ngettext.calls == [
            pretend.call("Test %(foo)s", "Plural %(foos)s", 1),
        ]


class TestJinjaRequestTranslation:

    def test_stores_domain(self):
        domain = pretend.stub()
        assert translations.JinjaRequestTranslation(domain).domain is domain

    def test_calls_translation_gettext(self):
        gettext = pretend.call_recorder(lambda m: "A translated message")

        context = {
            "request": pretend.stub(translation=pretend.stub(gettext=gettext)),
        }

        rt = translations.JinjaRequestTranslation(pretend.stub())
        translated = rt.gettext(context, "A testing message")

        assert translated == "A translated message"
        assert gettext.calls == [pretend.call("A testing message")]

    def test_calls_translation_ngettext(self):
        ngettext = pretend.call_recorder(lambda m, p, n: "translated message")

        context = {
            "request": pretend.stub(
                translation=pretend.stub(ngettext=ngettext),
            ),
        }

        rt = translations.JinjaRequestTranslation(pretend.stub())
        translated = rt.ngettext(
            context, "A testing message", "Another testing message", 4,
        )

        assert translated == "translated message"
        assert ngettext.calls == [
            pretend.call("A testing message", "Another testing message", 4),
        ]


class TestTranslateValue:

    def test_with_non_translate_string(self):
        value = pretend.stub()
        assert translations.translate_value(None, value) is value

    def test_with_translate_string(self):
        translation = pretend.stub()
        context = {"request": pretend.stub(translation=translation)}
        ts = translations.TranslationString("A Message")
        ts.translate = pretend.call_recorder(lambda t: "translated message")

        translated = translations.translate_value(context, ts)

        assert translated == "translated message"
        assert ts.translate.calls == [pretend.call(translation)]


class TestSimpleAPI:

    def test_gettext_no_kwargs(self):
        ts = translations.gettext("My Message")
        assert isinstance(ts, translations.TranslationString)
        assert ts.message_id == "My Message"
        assert ts.plural is None
        assert ts.n is None
        assert ts.mapping == {}

    def test_gettext_with_kwargs(self):
        ts = translations.gettext("My Message", foo="bar")
        assert isinstance(ts, translations.TranslationString)
        assert ts.message_id == "My Message"
        assert ts.plural is None
        assert ts.n is None
        assert ts.mapping == {"foo": "bar"}

    def test_ngettext_no_n(self):
        ts_p = translations.ngettext("M1", "M2")
        ts = ts_p(3)
        assert isinstance(ts, translations.TranslationString)
        assert ts.message_id == "M1"
        assert ts.plural == "M2"
        assert ts.n == 3
        assert ts.mapping == {}

    def test_ngettext_with_n(self):
        ts = translations.ngettext("M1", "M2", 6)
        assert isinstance(ts, translations.TranslationString)
        assert ts.message_id == "M1"
        assert ts.plural == "M2"
        assert ts.n == 6
        assert ts.mapping == {}

    def test_ngettext_with_kwargs(self):
        ts = translations.ngettext("M1", "M2", 6, foo="bar")
        assert isinstance(ts, translations.TranslationString)
        assert ts.message_id == "M1"
        assert ts.plural == "M2"
        assert ts.n == 6
        assert ts.mapping == {"foo": "bar"}
