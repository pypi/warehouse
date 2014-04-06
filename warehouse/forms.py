# Copyright 2014 Donald Stufft
#
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
import babel.support

from wtforms import validators, widgets  # noqa
from wtforms.fields import *  # noqa
from wtforms.form import Form as _Form
from wtforms.validators import ValidationError  # noqa


class Form(_Form):

    def __init__(self, *args, translations=None, **kwargs):
        if translations is None:
            translations = babel.support.NullTranslations()

        self._translations = translations

        super(Form, self).__init__(*args, **kwargs)

    def _get_translations(self):
        return self._translations

    def gettext(self, string):
        return self._translations.gettext(string)

    def ngettext(self, singular, plural, n):
        return self._translations.ngettext(singular, plural, n)
