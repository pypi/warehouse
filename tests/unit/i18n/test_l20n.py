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

from warehouse.i18n import l20n


@pytest.mark.parametrize(
    ("tid", "args", "expected"),
    [
        ("foo", {}, 'data-l10n-id="foo"'),
        (
            "bar",
            {"thing": "other"},
            'data-l10n-id="bar" '
            'data-l10n-args="{&#34;thing&#34;:&#34;other&#34;}"',
        ),
    ],
)
def test_l20n(tid, args, expected):
    assert l20n.l20n(tid, **args) == expected
