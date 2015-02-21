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

import jinja2
import pytest
import readme.rst

from warehouse import filters


class TestReadmeRender:

    def test_can_render(self, monkeypatch):
        monkeypatch.setattr(
            readme.rst, "render", lambda raw: ("rendered", True)
        )

        result = filters.readme_renderer("raw thing", format="rst")

        assert result == jinja2.Markup("rendered")

    def test_cant_render(self, monkeypatch):
        monkeypatch.setattr(
            readme.rst, "render", lambda raw: ("unrendered\nthing", False)
        )

        result = filters.readme_renderer("raw thing", format="rst")

        assert result == jinja2.Markup("unrendered<br>\nthing")


@pytest.mark.parametrize(
    ("inp", "expected"),
    [
        (1, "1"),
        (999, "999"),
        (1234, "1.23k"),
        (4304264, "4.3M"),
        (7878123132, "7.88G"),
        (9999999999999, "10T"),
    ],
)
def test_SI_symbol(inp, expected):
    assert filters.SI_symbol(inp) == expected
