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

from pyramid.i18n import TranslationStringFactory, default_locale_negotiator

# from pyramid.threadlocal import get_current_request

KNOWN_LOCALES = {"en": "English", "de": "German"}

LOCALE_ATTR = "_LOCALE_"

localize = TranslationStringFactory("messages")


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


# def localize(message, **kwargs):
#     request = get_current_request()
#     return request.localizer.translate(_translation_factory(message, **kwargs))


def includeme(config):
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
