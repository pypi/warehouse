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

import collections.abc
import functools

from jinja2 import contextfunction
from pyramid.threadlocal import get_current_request


class TranslationString:

    def __init__(self, message_id, plural=None, n=None, mapping=None):
        if mapping is None:
            mapping = {}

        self.message_id = message_id
        self.plural = plural
        self.n = n
        self.mapping = mapping

        if bool(self.plural) != bool(self.n):
            raise ValueError("Must specify plural and n together.")

    def __repr__(self):
        extra = ""
        if self.plural is not None:
            extra = " plural={!r} n={!r}".format(self.plural, self.n)
        return "<TranslationString: message_id={!r}{}>".format(
            self.message_id,
            extra,
        )

    def __mod__(self, mapping):
        if not isinstance(mapping, collections.abc.Mapping):
            raise TypeError("Only mappings are supported.")

        vals = self.mapping.copy()
        vals.update(mapping)

        return TranslationString(
            self.message_id, self.plural, self.n, mapping=vals,
        )

    def translate(self, translation):
        if self.plural is not None:
            result = translation.ngettext(self.message_id, self.plural, self.n)
        else:
            result = translation.gettext(self.message_id)

        return result % self.mapping


class JinjaRequestTranslation:

    def __init__(self, domain):
        self.domain = domain

    @contextfunction
    def gettext(self, ctx, *args, **kwargs):
        request = ctx.get("request") or get_current_request()
        return request.translation.gettext(*args, **kwargs)

    @contextfunction
    def ngettext(self, ctx, *args, **kwargs):
        request = ctx.get("request") or get_current_request()
        return request.translation.ngettext(*args, **kwargs)


@contextfunction
def translate_value(ctx, value):
    if isinstance(value, TranslationString):
        return value.translate(ctx["request"].translation)

    return value


def gettext(message_id, **kwargs):
    return TranslationString(message_id, mapping=kwargs)


def ngettext(message_id, plural, n=None, **kwargs):
    if n is None:
        return functools.partial(
            TranslationString, message_id, plural, mapping=kwargs
        )

    return TranslationString(message_id, plural, n, mapping=kwargs)
