# SPDX-License-Identifier: Apache-2.0
import jinja2
import pytest

from pyramid_jinja2 import SmartAssetSpecLoader


@pytest.fixture
def env():
    """A Jinja2 environment that resolves asset-spec template names.

    The whitespace flags match the `.html` renderer's (warehouse/config.py), so
    rendered output here is the shipped output. Warehouse's filters and globals
    are not wired up: a component template reaching for one (`|shorten_number`,
    `now()`, `Permissions`) fails here while working in the app, so keep component
    templates to plain props.
    """
    return jinja2.Environment(
        autoescape=True,
        loader=SmartAssetSpecLoader(),
        extensions=["pyramid_components.jinja2.ComponentExtension"],
        lstrip_blocks=True,
        trim_blocks=True,
    )
