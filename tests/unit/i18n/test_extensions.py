# SPDX-License-Identifier: Apache-2.0

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
        autoescape=True,
        extensions=["jinja2.ext.i18n", *ext],
    )

    class Faketext:
        # Every method is identity
        def __getattribute__(self, _: str):
            return lambda x: x

    env.install_gettext_translations(Faketext())

    # Result is trimmed
    assert env.from_string("{% trans %}   hey   {% endtrans %}").render() == result


class TestFallbackInternationalizationExtension:
    @pytest.mark.parametrize(
        ("newstyle_env", "newstyle_param", "newer_called", "pgettext", "npgettext"),
        [
            (True, True, True, False, False),
            (True, None, True, False, False),
            (False, True, True, True, True),
            (False, None, False, True, True),
        ],
    )
    def test_install(
        self,
        mocker,
        newstyle_env,
        newstyle_param,
        newer_called,
        pgettext,
        npgettext,
    ):
        make_newer_gettext = mocker.patch.object(
            extensions, "_make_newer_gettext", autospec=True, side_effect=lambda f: f
        )
        make_newer_ngettext = mocker.patch.object(
            extensions, "_make_newer_ngettext", autospec=True, side_effect=lambda f: f
        )

        gettext = mocker.stub(name="gettext")
        ngettext = mocker.stub(name="ngettext")

        env = Environment(
            autoescape=True,
            extensions=[
                "warehouse.i18n.extensions.FallbackInternationalizationExtension"
            ],
        )
        env.newstyle_gettext = newstyle_env
        env.install_gettext_callables(
            gettext,
            ngettext,
            newstyle=newstyle_param,
            pgettext=mocker.stub(name="pgettext") if pgettext else None,
            npgettext=mocker.stub(name="npgettext") if npgettext else None,
        )

        if newer_called:
            make_newer_gettext.assert_called_once_with(gettext)
            make_newer_ngettext.assert_called_once_with(ngettext)
        else:
            make_newer_gettext.assert_not_called()
            make_newer_ngettext.assert_not_called()

    @pytest.mark.parametrize(
        ("translation", "expected"),
        [
            ("Youzer: %(user)s", "Youzer: monty"),
            ("Youzer: %(missing)s", "User: monty"),
            ("Youzer: %（user）", "User: monty"),  # noqa: RUF001 forces failure
        ],
    )
    def test_gettext_fallback(self, mocker, translation, expected):
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
            autoescape=True,
            loader=DictLoader(templates),
            extensions=[
                "warehouse.i18n.extensions.FallbackInternationalizationExtension"
            ],
        )
        env.install_gettext_callables(
            gettext, mocker.stub(name="ngettext"), newstyle=True
        )

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
                "%（user_num）s Youzer online",  # noqa: RUF001 forces failure
                "%（user_num）s Youzers online",  # noqa: RUF001 forces failure
                1,
                "1 User online",
            ),
            (
                "%（user_num）s Youzer online",  # noqa: RUF001 forces failure
                "%（user_num）s Youzers online",  # noqa: RUF001 forces failure
                2,
                "2 Users online",
            ),
        ],
    )
    def test_ngettext_fallback(
        self, mocker, translation, translation_plural, num, expected
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
            autoescape=True,
            loader=DictLoader(templates),
            extensions=[
                "warehouse.i18n.extensions.FallbackInternationalizationExtension"
            ],
        )
        env.install_gettext_callables(
            mocker.stub(name="gettext"), ngettext, newstyle=True
        )

        tmpl = env.get_template("test.html")
        assert tmpl.render(LANGUAGE="en_US", user_num=num) == expected
