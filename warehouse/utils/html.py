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

from jinja2 import nodes
from jinja2.ext import Extension


class ClientSideIncludeExtension(Extension):
    """
    This extension adds support for a "Client side Include", which will be
    included into the final page using javascript instead of on the server. It
    is used like:

        {% csi "/some/url/" %}
        {% endcsi %}

    Which will render as an empty div that will be replaced using javascript.
    You may place default content inside of this div (in case js is disabled,
    the include fails for some reason, or to render before the include happens)
    by filling in the area between the two block tags, thus something like:

        {% csi "/some/url/" %}
            <p>You need Javascript Enabled to See this Content</p>
        {% endcsi %}

    Would render a client side include that instructs the user they need JS
    if the CSI doesn't happen for one reason or another.
    """

    tags = {"csi"}

    def parse(self, parser):
        # the first token is the token that started the tag.  In our case
        # we only listen to ``'csi'`` so this will be a name token with
        # `csi` as value.  We get the line number so that we can give that line
        # number to the nodes we create by hand.
        lineno = next(parser.stream).lineno

        # Now we parse a single expression that is used as the URL we're going
        # to include
        url = parser.parse_expression()

        # Now we parse the body of the csi block up to `endcsi` and drop the
        # needle (which would always be `endcsi` in that case).
        body = parser.parse_statements(["name:endcsi"], drop_needle=True)

        # Now return a `CallBlock` node that calls our _csi helper method on
        # this extension.
        n = nodes.CallBlock(self.call_method("_csi", [url]), [], [], body)
        n = n.set_lineno(lineno)
        return n

    def _csi(self, url, caller):
        return f'<div data-html-include="{url}">{caller()}</div>'
