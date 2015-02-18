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
import readme.rst


def readme_renderer(value, *, format):
    # The format parameter is here so we can more easily expand this to cover
    # READMEs which do not use restructuredtext, but for now rst is the only
    # format we support.
    assert format == "rst", "We currently only support rst rendering."

    # Actually render the given value, this will not only render the value, but
    # also ensure that it's had any disallowed markup removed.
    value, rendered = readme.rst.render(value)

    # If the content was not rendered, we'll replace the newlines with breaks
    # so that it shows up nicer when rendered.
    if not rendered:
        value = value.replace("\n", "<br>\n")

    return jinja2.Markup(value)
