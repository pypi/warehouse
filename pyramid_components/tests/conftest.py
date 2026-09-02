# SPDX-License-Identifier: Apache-2.0
import jinja2
import pytest

from pyramid_components import registry as registry_module


@pytest.fixture(autouse=True)
def isolate_registry():
    """Snapshot and restore the module-level registry around each test.

    Keeps tests isolated and preserves any registrations made at import time
    (e.g. warehouse admin components registered when their module is imported).
    """
    saved = dict(registry_module._registry)
    try:
        yield registry_module
    finally:
        registry_module._registry.clear()
        registry_module._registry.update(saved)


@pytest.fixture
def make_env(tmp_path):
    """Build a Jinja2 environment with the component extension and a template dir."""

    def _make(files: dict[str, str]):
        for name, source in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        return jinja2.Environment(
            autoescape=True,
            loader=jinja2.FileSystemLoader(str(tmp_path)),
            extensions=["pyramid_components.jinja2.ComponentExtension"],
        )

    return _make
