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


def _locale(request):
    """
    Computes a babel.core:Locale() object for this request.
    """
    return Locale.parse(request.locale_name)


def includeme(config):
    # Add the request attributes
    config.add_request_method(_locale, name="locale", reify=True)

    # Register our i18n/l10n filters for Jinja2
    filters = config.get_settings().setdefault("jinja2.filters", {})
    filters.setdefault("format_date", "warehouse.i18n.filters:format_date")
    filters.setdefault(
        "format_datetime",
        "warehouse.i18n.filters:format_datetime",
    )
    filters.setdefault(
        "format_rfc822_datetime",
        "warehouse.i18n.filters:format_rfc822_datetime",
    )

    # Register our utility functions with Jinja2
    jglobals = config.get_settings().setdefault("jinja2.globals", {})
    jglobals.setdefault("l20n", "warehouse.i18n.l20n:l20n")
