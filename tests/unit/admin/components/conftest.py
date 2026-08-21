# SPDX-License-Identifier: Apache-2.0
import jinja2
import pytest

from pyramid_jinja2 import SmartAssetSpecLoader


@pytest.fixture
def env():
    """A Jinja2 environment that resolves asset-spec template names."""
    return jinja2.Environment(
        autoescape=True,
        loader=SmartAssetSpecLoader(),
        extensions=["pyramid_components.jinja2.ComponentExtension"],
    )
