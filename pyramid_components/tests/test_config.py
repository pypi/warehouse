# SPDX-License-Identifier: Apache-2.0
from pyramid_components import config as config_module

EXT = "pyramid_components.jinja2.ComponentExtension"


class _FakeConfig:
    def __init__(self, settings):
        self._settings = settings
        self.included = []
        self.extensions = []

    def get_settings(self):
        return self._settings

    def include(self, name):
        self.included.append(name)

    def add_jinja2_extension(self, ext, name):
        self.extensions.append((ext, name))


def test_includeme_registers_extension_on_html_renderer_by_default():
    config = _FakeConfig({})

    config_module.includeme(config)

    assert config.included == ["pyramid_jinja2"]
    assert config.extensions == [(EXT, ".html")]


def test_includeme_renderer_name_is_configurable():
    config = _FakeConfig({"pyramid_components.renderer_name": ".jinja2"})

    config_module.includeme(config)

    assert config.extensions == [(EXT, ".jinja2")]
