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

import os.path

from babel.core import Locale
from babel.support import Translations

from warehouse.i18n.translations import (
    JinjaRequestTranslation, translate_value, gettext, ngettext,
)


__all__ = ["gettext", "ngettext", "includeme"]


GETTEXT_DOMAIN = "warehouse"

LOCALE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "translations")
)


def _locale(request):
    """
    Computes a babel.core:Locale() object for this request.
    """
    return Locale.parse(request.locale_name)


def _translation(request):
    """
    Loads a translation object for this request.
    """
    # TODO: Should we cache these in memory?
    return Translations.load(LOCALE_DIR, request.locale, domain=GETTEXT_DOMAIN)


def includeme(config):
    # Add the request attributes
    config.add_request_method(_locale, name="locale", reify=True)
    config.add_request_method(_translation, name="translation", reify=True)

    # Register our i18n/l10n filters for Jinja2
    filters = config.get_settings().setdefault("jinja2.filters", {})
    filters.setdefault("format_date", "warehouse.i18n.filters:format_date")
    filters.setdefault(
        "format_datetime",
        "warehouse.i18n.filters:format_datetime",
    )

    # Register our finalize function for Jinja2
    config.get_settings()["jinja2.finalize"] = translate_value

    # Configure Jinja2 for translation
    config.get_settings()["jinja2.i18n.domain"] = GETTEXT_DOMAIN
    config.get_settings()["jinja2.i18n.gettext"] = JinjaRequestTranslation
