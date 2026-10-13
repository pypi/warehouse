# SPDX-License-Identifier: Apache-2.0
import pytest

from pyramid_components import registry
from warehouse.admin.components.info_box import InfoBox
from warehouse.admin.components.stat_card import StatCard


@pytest.mark.parametrize(
    ("name", "expected"),
    [("admin.stat_card", StatCard), ("admin.info_box", InfoBox)],
)
def test_component_is_registered_on_import(name, expected):
    """`registry.get` resolves names at render time, so an import must have run.

    Only importing `warehouse.admin.components` populates the registry.
    """
    assert registry.get(name) is expected
