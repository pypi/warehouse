# SPDX-License-Identifier: Apache-2.0
from pyramid_components.component import Component
from pyramid_components.config import includeme
from pyramid_components.registry import register

import pyramid_components as pc


def test_public_names_are_reexported():
    assert pc.Component is Component
    assert pc.register is register
    assert pc.includeme is includeme


def test_dunder_all_is_defined():
    assert set(pc.__all__) == {"Component", "register", "includeme"}
