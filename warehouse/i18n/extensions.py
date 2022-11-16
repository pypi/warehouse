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

import typing as t

from jinja2.ext import (
    Extension,
    InternationalizationExtension,
    _make_new_npgettext,
    _make_new_pgettext,
)
from jinja2.runtime import Context
from jinja2.utils import pass_context
from markupsafe import Markup


class TrimmedTranslatableTagsExtension(Extension):
    """
    This extension ensures all {% trans %} tags are trimmed by default.
    """

    def __init__(self, environment):
        environment.policies["ext.i18n.trimmed"] = True

def _make_new_gettext(func: t.Callable[[str], str]) -> t.Callable[..., str]:
    @pass_context
    def gettext(__context: Context, __string: str, **variables: t.Any) -> str:
        rv = __context.call(func, __string)
        if __context.eval_ctx.autoescape:
            rv = Markup(rv)
        # Always treat as a format string, even if there are no
        # variables. This makes translation strings more consistent
        # and predictable. This requires escaping
        try:
            return rv % variables  # type: ignore
        except KeyError:
            return __string % variables

    return gettext


def _make_new_ngettext(func: t.Callable[[str, str, int], str]) -> t.Callable[..., str]:
    @pass_context
    def ngettext(
        __context: Context,
        __singular: str,
        __plural: str,
        __num: int,
        **variables: t.Any,
    ) -> str:
        variables.setdefault("num", __num)
        rv = __context.call(func, __singular, __plural, __num)
        if __context.eval_ctx.autoescape:
            rv = Markup(rv)
        # Always treat as a format string, see gettext comment above.
        try:
            return rv % variables  # type: ignore
        except KeyError:
            if __num > 1:
                return __plural % variables
            return __singular % variables

    return ngettext


class FallbackInternationalizationExtension(InternationalizationExtension):
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
            gettext = _make_new_gettext(gettext)
            ngettext = _make_new_ngettext(ngettext)

            if pgettext is not None:
                pgettext = _make_new_pgettext(pgettext)

            if npgettext is not None:
                npgettext = _make_new_npgettext(npgettext)

        self.environment.globals.update(
            gettext=gettext, ngettext=ngettext, pgettext=pgettext, npgettext=npgettext
        )
