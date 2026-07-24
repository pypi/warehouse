# SPDX-License-Identifier: Apache-2.0
"""The ``{% component %}`` Jinja2 tag.

Syntax: ``{% component "name", key=expr, key2=expr2 %}``

The name and every keyword expression are parsed as ordinary Jinja2 expressions, so they
evaluate in the *parent* template's context. The rendered component, however, sees only
the context returned by its ``get_context`` (see registry.render) — an isolated context.
In particular, per-render variables that pyramid_jinja2 injects into page templates
(``request``, ``context``) are *not* available inside component templates; evaluate
request-dependent expressions in the parent and pass the results in as props.
"""

from jinja2 import nodes
from jinja2.ext import Extension

from pyramid_components import registry


class ComponentExtension(Extension):
    tags = {"component"}

    def parse(self, parser):
        lineno = next(parser.stream).lineno  # consume the 'component' token
        name = parser.parse_expression()
        kwargs = []
        while parser.stream.current.type != "block_end":
            parser.stream.expect("comma")
            key = parser.stream.expect("name").value
            parser.stream.expect("assign")
            value = parser.parse_expression()
            kwargs.append(nodes.Keyword(key, value, lineno=value.lineno))
        call = self.call_method("_render", args=[name], kwargs=kwargs, lineno=lineno)
        return nodes.Output([call], lineno=lineno)

    def _render(self, name, /, **kwargs):
        # `name` is positional-only so it can never collide with a component
        # prop of the same name passed via kwargs.
        return registry.render(name, self.environment, **kwargs)
