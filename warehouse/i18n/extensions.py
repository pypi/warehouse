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
    def gettext(__context: Context, __string: str, **variables: t.Any) -> str:
        try:
            return _old_gettext(__context, __string, **variables)
        except (KeyError, ValueError):
            return __string % variables

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
        __context: Context,
        __singular: str,
        __plural: str,
        __num: int,
        **variables: t.Any,
    ) -> str:
        try:
            return _old_ngettext(__context, __singular, __plural, __num, **variables)
        except (KeyError, ValueError):
            if __num > 1:
                return __plural % variables
            return __singular % variables

    return ngettext


class FallbackInternationalizationExtension(InternationalizationExtension):
    """
    Replica of InternationalizationExtension which overrides a single
    method _install_callables to inject our own wrappers for gettext
    and ngettext with the _make_newer_gettext and _make_newer_ngettext
    defined above.

    Diff from original method is:

    -            gettext = _make_new_gettext(gettext)
    -            ngettext = _make_new_ngettext(ngettext)
    +            gettext = _make_newer_gettext(gettext)
    +            ngettext = _make_newer_ngettext(ngettext)
    """

    def _install_callables(
        self,
        gettext: t.Callable[[str], str],
        ngettext: t.Callable[[str, str, int], str],
        newstyle: t.Optional[bool] = None,
        pgettext: t.Optional[t.Callable[[str, str], str]] = None,
        npgettext: t.Optional[t.Callable[[str, str, str, int], str]] = None,
    ) -> None:
        if newstyle is not None:
            self.environment.newstyle_gettext = newstyle  # type: ignore
        if self.environment.newstyle_gettext:  # type: ignore
            gettext = _make_newer_gettext(gettext)
            ngettext = _make_newer_ngettext(ngettext)

            if pgettext is not None:
                pgettext = _make_new_pgettext(pgettext)

            if npgettext is not None:
                npgettext = _make_new_npgettext(npgettext)

        self.environment.globals.update(
            gettext=gettext, ngettext=ngettext, pgettext=pgettext, npgettext=npgettext
        )
