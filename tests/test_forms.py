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
import pretend

import babel.support

from warehouse.forms import Form


class TestForm:

    def test_get_translations(self):
        translations = pretend.stub()
        form = Form(translations=translations)
        assert form._get_translations() is translations

    def test_get_translations_none(self):
        assert isinstance(
            Form(translations=None)._get_translations(),
            babel.support.NullTranslations,
        )

    def test_gettext(self):
        translations = pretend.stub(gettext=pretend.call_recorder(lambda s: s))
        form = Form(translations=translations)

        assert form.gettext("What") == "What"
        assert translations.gettext.calls == [pretend.call("What")]

    def test_ngettext(self):
        translations = pretend.stub(
            ngettext=pretend.call_recorder(lambda s, p, n: s),
        )
        form = Form(translations=translations)

        assert form.ngettext("One Time", "Many Times", 1) == "One Time"
        assert translations.ngettext.calls == [
            pretend.call("One Time", "Many Times", 1),
        ]
