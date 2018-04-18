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

from warehouse.utils import readme


def test_render_with_none():
    result = readme.render(None)
    assert result is None


def test_can_render_rst():
    result = readme.render("raw thing", "text/x-rst")
    assert result == "<p>raw thing</p>\n"


def test_cant_render_rst():
    result = readme.render("raw `<thing", "text/x-rst")
    assert result == "raw `&lt;thing"


def test_can_render_plaintext():
    result = readme.render("raw thing", "text/plain")
    assert result == "raw thing"


def test_can_render_markdown():
    result = readme.render("raw thing", "text/markdown")
    assert result == "<p>raw thing</p>\n"


def test_can_render_missing_content_type():
    result = readme.render("raw thing")
    assert result == "<p>raw thing</p>\n"


def test_renderer_version():
    assert readme.renderer_version() is not None
