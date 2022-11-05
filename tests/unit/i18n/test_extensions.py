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

import pytest

from jinja2 import Environment


@pytest.mark.parametrize(
    "ext, result",
    [
        # Just a sanity check: test that when we do nothing, text is not trimmed.
        ([], "   hey   "),
        # Now test that with our extension, text is trimmed.
        (["warehouse.i18n.extensions.TrimmedTranslatableTagsExtension"], "hey"),
    ],
)
def test_trim_trans_tags(ext, result):
    env = Environment(
        extensions=["jinja2.ext.i18n"] + ext,
    )

    class Faketext:
        # Every method is identity
        def __getattribute__(self, _: str):
            return lambda x: x

    env.install_gettext_translations(Faketext())

    # Result is trimmed
    assert env.from_string("{% trans %}   hey   {% endtrans %}").render() == result
