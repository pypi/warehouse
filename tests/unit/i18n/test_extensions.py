# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from jinja2 import DictLoader, Environment, pass_context

from warehouse.i18n import extensions


@pytest.mark.parametrize(
    ("ext", "result"),
    [
        # Just a sanity check: test that when we do nothing, text is not trimmed.
        ([], "   hey   "),
        # Now test that with our extension, text is trimmed.
        (["warehouse.i18n.extensions.TrimmedTranslatableTagsExtension"], "hey"),
    ],
)
def test_trim_trans_tags(ext, result):
    env = Environment(
        extensions=["jinja2.ext.i18n"] + ext,
    )

    class Faketext:
        # Every method is identity
        def __getattribute__(self, _: str):
            return lambda x: x

    env.install_gettext_translations(Faketext())

    # Result is trimmed
    assert env.from_string("{% trans %}   hey   {% endtrans %}").render() == result


pretend_gettext = pretend.call_recorder(lambda message: message)
pretend_ngettext = pretend.call_recorder(
    lambda singular, plural, n: singular if n == 1 else plural
)
pretend_pgettext = pretend.call_recorder(lambda context, message: message)
pretend_npgettext = pretend.call_recorder(
    lambda context, singular, plural, n: singular if n == 1 else plural
)


class TestFallbackInternationalizationExtension:
    @pytest.mark.parametrize(
        (
            "newstyle_env",
            "newstyle_param",
            "newer_gettext_expected",
            "newer_ngettext_expected",
            "pgettext",
            "npgettext",
        ),
        [
            (
                True,
                True,
                [pretend.call(pretend_gettext)],
                [pretend.call(pretend_ngettext)],
                False,
                False,
            ),
            (
                True,
                None,
                [pretend.call(pretend_gettext)],
                [pretend.call(pretend_ngettext)],
                False,
                False,
            ),
            (
                False,
                True,
                [pretend.call(pretend_gettext)],
                [pretend.call(pretend_ngettext)],
                True,
                True,
            ),
            (False, None, [], [], True, True),
        ],
    )
    def test_install(
        self,
        monkeypatch,
        newstyle_env,
        newstyle_param,
        newer_gettext_expected,
        newer_ngettext_expected,
        pgettext,
        npgettext,
    ):
        _make_newer_gettext = pretend.call_recorder(lambda func: func)
        _make_newer_ngettext = pretend.call_recorder(lambda func: func)

        monkeypatch.setattr(extensions, "_make_newer_gettext", _make_newer_gettext)
        monkeypatch.setattr(extensions, "_make_newer_ngettext", _make_newer_ngettext)

        env = Environment(
            extensions=[
                "warehouse.i18n.extensions.FallbackInternationalizationExtension"
            ],
        )
        env.newstyle_gettext = newstyle_env
        env.install_gettext_callables(
            pretend_gettext,
            pretend_ngettext,
            newstyle=newstyle_param,
            pgettext=pretend_pgettext if pgettext else None,
            npgettext=pretend_npgettext if npgettext else None,
        )

        assert _make_newer_gettext.calls == newer_gettext_expected
        assert _make_newer_ngettext.calls == newer_ngettext_expected

    @pytest.mark.parametrize(
        ("translation", "expected"),
        [
            ("Youzer: %(user)s", "Youzer: monty"),
            ("Youzer: %(missing)s", "User: monty"),
            ("Youzer: %（user）", "User: monty"),
        ],
    )
    def test_gettext_fallback(self, translation, expected):
        templates = {"test.html": "{% trans %}User: {{ user }}{% endtrans %}"}
        languages = {
            "en_US": {
                "User: %(user)s": translation,
            }
        }

        @pass_context
        def gettext(context, string):
            language = context.get("LANGUAGE", "en")
            return languages.get(language, {}).get(string, string)

        env = Environment(
            loader=DictLoader(templates),
            extensions=[
                "warehouse.i18n.extensions.FallbackInternationalizationExtension"
            ],
        )
        env.install_gettext_callables(gettext, pretend_ngettext, newstyle=True)

        tmpl = env.get_template("test.html")
        assert tmpl.render(LANGUAGE="en_US", user="monty") == expected

    @pytest.mark.parametrize(
        ("translation", "translation_plural", "num", "expected"),
        [
            (
                "%(user_num)s Youzer online",
                "%(user_num)s Youzers online",
                1,
                "1 Youzer online",
            ),
            (
                "%(user_num)s Youzer online",
                "%(user_num)s Youzers online",
                2,
                "2 Youzers online",
            ),
            (
                "%(missing)s Youzer online",
                "%(missing)s Youzers online",
                1,
                "1 User online",
            ),
            (
                "%(missing)s Youzer online",
                "%(missing)s Youzers online",
                2,
                "2 Users online",
            ),
            (
                "%（user_num）s Youzer online",
                "%（user_num）s Youzers online",
                1,
                "1 User online",
            ),
            (
                "%（user_num）s Youzer online",
                "%（user_num）s Youzers online",
                2,
                "2 Users online",
            ),
        ],
    )
    def test_ngettext_fallback(
        self, monkeypatch, translation, translation_plural, num, expected
    ):
        templates = {
            "test.html": (
                "{% trans user_num %}{{ user_num }} User online"
                "{% pluralize user_num %}{{ user_num }} Users online{% endtrans %}"
            ),
        }
        languages = {
            "en_US": {
                "%(user_num)s User online": translation,
                "%(user_num)s Users online": translation_plural,
            }
        }

        @pass_context
        def ngettext(context, s, p, n):
            language = context.get("LANGUAGE", "en")
            if n != 1:
                return languages.get(language, {}).get(p, p)
            return languages.get(language, {}).get(s, s)

        env = Environment(
            loader=DictLoader(templates),
            extensions=[
                "warehouse.i18n.extensions.FallbackInternationalizationExtension"
            ],
        )
        env.install_gettext_callables(pretend_gettext, ngettext, newstyle=True)

        tmpl = env.get_template("test.html")
        assert tmpl.render(LANGUAGE="en_US", user_num=num) == expected
