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

"""Utils for rendering and updating package descriptions (READMEs)."""

import cgi

import pkg_resources
import readme_renderer.markdown
import readme_renderer.rst
import readme_renderer.txt


_RENDERERS = {
    None: readme_renderer.rst,  # Default if description_content_type is None
    '': readme_renderer.rst,  # Default if description_content_type is None
    'text/plain': readme_renderer.txt,
    'text/x-rst': readme_renderer.rst,
    'text/markdown': readme_renderer.markdown,
}


def render(value, content_type=None):
    if value is None:
        return value

    content_type, parameters = cgi.parse_header(content_type or '')

    # Get the appropriate renderer
    renderer = _RENDERERS.get(content_type, readme_renderer.txt)

    # Actually render the given value, this will not only render the value, but
    # also ensure that it's had any disallowed markup removed.
    rendered = renderer.render(value, **parameters)

    # If the content was not rendered, we'll render as plaintext instead. The
    # reason it's necessary to do this instead of just accepting plaintext is
    # that readme_renderer will deal with sanitizing the content.
    if rendered is None:
        rendered = readme_renderer.txt.render(value)

    return rendered


def renderer_version():
    return pkg_resources.get_distribution('readme-renderer').version
