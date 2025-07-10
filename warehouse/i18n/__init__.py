# SPDX-License-Identifier: Apache-2.0

import functools

from babel.core import Locale
from pyramid import viewderivers
from pyramid.i18n import TranslationStringFactory, default_locale_negotiator
from pyramid.threadlocal import get_current_request

from warehouse.cache.http import add_vary

from .extensions import FallbackInternationalizationExtension

KNOWN_LOCALES = {
    identifier: Locale.parse(identifier, sep="_")
    for identifier in [
        "en",  # English
        "es",  # Spanish
        "fr",  # French
        "ja",  # Japanese
        "pt_BR",  # Brazilian Portuguese
        "uk",  # Ukrainian
        "el",  # Greek
        "de",  # German
        "zh_Hans",  # Simplified Chinese
        "zh_Hant",  # Traditional Chinese
        "ru",  # Russian
        "he",  # Hebrew
        "eo",  # Esperanto
        "ko",  # Korean
    ]
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

    def __eq__(self, other):
        return (
            self.args == other.args and self.kwargs == other.kwargs
            if isinstance(other, LazyString)
            else self.args == (other,) and not self.kwargs
        )


def _locale(request):
    """
    Gets a babel.core:Locale() object for this request.
    """
    return KNOWN_LOCALES.get(request.locale_name, KNOWN_LOCALES["en"])


def _negotiate_locale(request):
    locale_name = default_locale_negotiator(request)
    if locale_name in KNOWN_LOCALES:
        return locale_name

    if request.accept_language:
        return request.accept_language.best_match(tuple(KNOWN_LOCALES.keys()))

    return None


def _localize(request, message, **kwargs):
    """
    To be used on the request directly, e.g. `request._(message)`
    """
    return request.localizer.translate(_translation_factory(message, **kwargs))


def localize(message, **kwargs):
    """
    To be used when we don't have the request context, e.g.
    `from warehouse.i18n import localize as _`
    """

    def _lazy_localize(message, **kwargs):
        request = get_current_request()
        return _localize(request, message, **kwargs)

    return LazyString(_lazy_localize, message, **kwargs)


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


translated_view.options = {"has_translations"}  # type: ignore


def includeme(config):
    # Add the request attributes
    config.add_request_method(_locale, name="locale", reify=True)
    config.add_request_method(_localize, name="_")

    # Register our translation directory.
    config.add_translation_dirs("warehouse:locale/")

    config.set_locale_negotiator(_negotiate_locale)

    config.get_settings().setdefault(
        "jinja2.i18n_extension", FallbackInternationalizationExtension
    )

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
