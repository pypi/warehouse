# SPDX-License-Identifier: Apache-2.0
"""Pyramid integration for pyramid_components.

``config.include("pyramid_components")`` registers the ``{% component %}`` Jinja2 tag
on the renderer named by the ``pyramid_components.renderer_name`` setting (default
``.html``), via pyramid_jinja2's ``add_jinja2_extension`` directive. Component template
search roots are the consuming app's responsibility (e.g.
``config.add_jinja2_search_path("components", name=".html")``).

That renderer must already be registered when this include runs: including
pyramid_jinja2 alone registers only ``.jinja2``, so a bare Configurator raises
``AttributeError: 'NoneType' object has no attribute 'add_extension'``. Call
``config.add_jinja2_renderer(".html")`` first, or point the setting at ``.jinja2``.
"""

EXTENSION = "pyramid_components.jinja2.ComponentExtension"


def includeme(config):
    config.include("pyramid_jinja2")
    renderer_name = config.get_settings().get(
        "pyramid_components.renderer_name", ".html"
    )
    config.add_jinja2_extension(EXTENSION, name=renderer_name)
