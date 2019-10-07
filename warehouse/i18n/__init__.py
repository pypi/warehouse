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

from babel.core import Locale
from pyramid.i18n import TranslationStringFactory, default_locale_negotiator
from pyramid.threadlocal import get_current_request

KNOWN_LOCALES = {"en": "English"}

LOCALE_ATTR = "_LOCALE_"

_translation_factory = TranslationStringFactory("messages")


class LazyString:
    def __init__(self, fn, *args, **kwargs):
        self.fn = fn
        self.args = args
        self.mapping = kwargs.get("mapping", {})
        self.kwargs = kwargs

    def __json__(self, request):
        return str(self)

    def __mod__(self, new_mapping):
        mapping = self.mapping.copy()
        mapping.update(new_mapping)
        return LazyString(self.fn, *self.args, mapping=new_mapping, **self.kwargs)

    def __str__(self):
        return self.fn(*self.args, **self.kwargs)


def _locale(request):
    """
    Computes a babel.core:Locale() object for this request.
    """
    return Locale.parse(request.locale_name, sep="_")


def _negotiate_locale(request):
    locale_name = getattr(request, LOCALE_ATTR, None)
    if locale_name is not None:
        return locale_name

    locale_name = request.params.get(LOCALE_ATTR)
    if locale_name is not None:
        return locale_name

    locale_name = request.cookies.get(LOCALE_ATTR)
    if locale_name is not None:
        return locale_name

    if not request.accept_language:
        return default_locale_negotiator(request)

    return request.accept_language.best_match(
        tuple(KNOWN_LOCALES.keys()), default_match=default_locale_negotiator(request)
    )


def localize(message, **kwargs):
    def _localize(message, **kwargs):
        request = get_current_request()
        return request.localizer.translate(_translation_factory(message, **kwargs))

    return LazyString(_localize, message, **kwargs)


def includeme(config):
    # Add the request attributes
    config.add_request_method(_locale, name="locale", reify=True)

    # Register our translation directory.
    config.add_translation_dirs("warehouse:locale/")

    config.set_locale_negotiator(_negotiate_locale)

    # Register our i18n/l10n filters for Jinja2
    filters = config.get_settings().setdefault("jinja2.filters", {})
    filters.setdefault("format_date", "warehouse.i18n.filters:format_date")
    filters.setdefault("format_datetime", "warehouse.i18n.filters:format_datetime")
    filters.setdefault(
        "format_rfc822_datetime", "warehouse.i18n.filters:format_rfc822_datetime"
    )
    filters.setdefault("format_number", "warehouse.i18n.filters:format_number")

    jglobals = config.get_settings().setdefault("jinja2.globals", {})
    jglobals.setdefault("KNOWN_LOCALES", "warehouse.i18n:KNOWN_LOCALES")
