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

import functools

from babel.core import Locale
from pyramid import viewderivers
from pyramid.i18n import TranslationStringFactory, default_locale_negotiator
from pyramid.threadlocal import get_current_request

from warehouse.cache.http import add_vary

KNOWN_LOCALES = {
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "ja": "日本語",
    "pt_BR": "Português (do Brasil)",
    "uk": "Українська",
}

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


class InvalidLocalizer:
    def _fail(self):
        raise RuntimeError("Cannot use localizer without has_translations=True")

    @property
    def locale_name(self):
        self._fail()

    def pluralize(self, *args, **kwargs):
        self._fail()

    def translate(self, *args, **kwargs):
        self._fail()


def translated_view(view, info):
    if info.options.get("has_translations"):
        # If this page can be translated, then we'll add a Vary: PyPI-Locale
        #   Vary header.
        # Note: This will give weird results if hitting PyPI directly instead of through
        #       the Fastly VCL which sets PyPI-Locale.
        return add_vary("PyPI-Locale")(view)
    elif info.exception_only:
        return view
    else:
        # If we're not using translations on this view, then we'll wrap the view
        # with a wrapper that just ensures that the localizer cannot be used.
        @functools.wraps(view)
        def wrapped(context, request):
            # This whole method is a little bit of an odd duck, we want to make
            # sure that we don't actually *access* request.localizer, because
            # doing so triggers the machinery to create a new localizer. So
            # instead we will dig into the request object __dict__ to
            # effectively do the same thing, just without triggering an access
            # on request.localizer.

            # Save the original session so that we can restore it once the
            # inner views have been called.
            nothing = object()
            original_localizer = request.__dict__.get("localizer", nothing)

            # This particular view hasn't been set to allow access to the
            # translations, so we'll just assign an InvalidLocalizer to
            # request.localizer
            request.__dict__["localizer"] = InvalidLocalizer()

            try:
                # Invoke the real view
                return view(context, request)
            finally:
                # Restore the original session so that things like
                # pyramid_debugtoolbar can access it.
                if original_localizer is nothing:
                    del request.__dict__["localizer"]
                else:
                    request.__dict__["localizer"] = original_localizer

        return wrapped


translated_view.options = {"has_translations"}


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

    config.add_view_deriver(
        translated_view, over="rendered_view", under=viewderivers.INGRESS
    )
