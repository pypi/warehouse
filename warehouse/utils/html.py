# SPDX-License-Identifier: Apache-2.0

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
        args = [parser.parse_expression()]

        # if there is a comma, the user provided a tag type.  If not use
        # 'div' as second parameter.
        if parser.stream.skip_if("comma"):
            args.append(parser.parse_expression())
        else:
            args.append(nodes.Const("div"))

        # Now we parse the body of the csi block up to `endcsi` and drop the
        # needle (which would always be `endcsi` in that case).
        body = parser.parse_statements(["name:endcsi"], drop_needle=True)

        # Now return a `CallBlock` node that calls our _csi helper method on
        # this extension.
        n = nodes.CallBlock(self.call_method("_csi", args), [], [], body)
        n = n.set_lineno(lineno)
        return n

    def _csi(self, url, tag, caller):
        return f'<{tag} data-html-include="{url}">{caller()}</{tag}>'
