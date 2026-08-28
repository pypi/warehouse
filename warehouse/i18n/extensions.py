# SPDX-License-Identifier: Apache-2.0

import typing as t

from jinja2.ext import (
    Extension,
    InternationalizationExtension,
    _make_new_gettext,
    _make_new_ngettext,
    _make_new_npgettext,
    _make_new_pgettext,
)
from jinja2.runtime import Context
from jinja2.utils import pass_context


class TrimmedTranslatableTagsExtension(Extension):
    """
    This extension ensures all {% trans %} tags are trimmed by default.
    """

    def __init__(self, environment):
        environment.policies["ext.i18n.trimmed"] = True


def _make_newer_gettext(func: t.Callable[[str], str]) -> t.Callable[..., str]:
    """
    Wraps upstream _make_new_gettext with the try/except for KeyError to
    fallback to untranslated strings when translations have not been updated
    with new named variables.
    """
    _old_gettext = _make_new_gettext(func)

    @pass_context
    def gettext(context: Context, string: str, /, **variables: t.Any) -> str:
        try:
            return _old_gettext(context, string, **variables)
        except KeyError, ValueError:
            return string % variables

    return gettext


def _make_newer_ngettext(
    func: t.Callable[[str, str, int], str],
) -> t.Callable[..., str]:
    """
    Wraps upstream _make_new_ngettext with the try/except for KeyError to
    fallback to untranslated strings when translations have not been updated
    with new named variables.
    """
    _old_ngettext = pass_context(_make_new_ngettext(func))

    @pass_context
    def ngettext(
        context: Context,
        singular: str,
        plural: str,
        num: int,
        /,
        **variables: t.Any,
    ) -> str:
        try:
            return _old_ngettext(context, singular, plural, num, **variables)
        except KeyError, ValueError:
            if num > 1:
                return plural % variables
            return singular % variables

    return ngettext


# GNU gettext stores a contextual message under "context\x04message", which is
# what pybabel compiles an `msgctxt` into.
CONTEXT_SEPARATOR = "\x04"


def _make_context_gettext(func: t.Callable[[str], str]) -> t.Callable[[str, str], str]:
    """
    Derive a pgettext from a plain gettext.

    pyramid_jinja2 installs only gettext and ngettext, so without this
    `{% trans "context" %}` renders a call to None. Looking the message up under
    its context-prefixed key is all a real pgettext does; a key that comes back
    unchanged had no translation, and the bare message is the fallback.
    """

    def pgettext(context: str, message: str) -> str:
        key = f"{context}{CONTEXT_SEPARATOR}{message}"
        translated = func(key)
        return message if translated == key else translated

    return pgettext


def _make_context_ngettext(
    func: t.Callable[[str, str, int], str],
) -> t.Callable[[str, str, str, int], str]:
    """
    Derive an npgettext from a plain ngettext, as _make_context_gettext does.

    The context prefixes the singular, since that is the key a catalog stores
    the plural forms under.
    """

    def npgettext(context: str, singular: str, plural: str, num: int) -> str:
        key = f"{context}{CONTEXT_SEPARATOR}{singular}"
        translated = func(key, plural, num)
        return singular if translated == key else translated

    return npgettext


class FallbackInternationalizationExtension(InternationalizationExtension):
    """
    Replica of InternationalizationExtension which overrides a single
    method _install_callables to inject our own wrappers for gettext
    and ngettext with the _make_newer_gettext and _make_newer_ngettext
    defined above, and to supply a pgettext/npgettext pair that our
    renderer never passes in.

    Diff from original method is:

    -            gettext = _make_new_gettext(gettext)
    -            ngettext = _make_new_ngettext(ngettext)
    +            gettext = _make_newer_gettext(gettext)
    +            ngettext = _make_newer_ngettext(ngettext)

    plus the pgettext/npgettext defaulting above the newstyle branch.
    """

    def _install_callables(
        self,
        gettext: t.Callable[[str], str],
        ngettext: t.Callable[[str, str, int], str],
        newstyle: bool | None = None,
        pgettext: t.Callable[[str, str], str] | None = None,
        npgettext: t.Callable[[str, str, str, int], str] | None = None,
    ) -> None:
        if newstyle is not None:
            self.environment.newstyle_gettext = newstyle  # type: ignore[attr-defined]

        # pyramid_jinja2 calls install_gettext_callables() with gettext and
        # ngettext only, so a template using `{% trans "context" %}` would
        # otherwise call None. Derive the contextual pair from the plain ones.
        if pgettext is None:
            pgettext = _make_context_gettext(gettext)
        if npgettext is None:
            npgettext = _make_context_ngettext(ngettext)

        if self.environment.newstyle_gettext:  # type: ignore[attr-defined]
            gettext = _make_newer_gettext(gettext)
            ngettext = _make_newer_ngettext(ngettext)
            pgettext = _make_new_pgettext(pgettext)
            npgettext = _make_new_npgettext(npgettext)

        self.environment.globals.update(
            gettext=gettext, ngettext=ngettext, pgettext=pgettext, npgettext=npgettext
        )
