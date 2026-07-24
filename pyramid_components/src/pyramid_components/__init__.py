# SPDX-License-Identifier: Apache-2.0
"""pyramid_components: reusable components for Pyramid + Jinja2 applications.

Import convention (house style):

    import pyramid_components as pc
"""

from pyramid_components.component import Component
from pyramid_components.config import includeme
from pyramid_components.registry import register

__all__ = ["Component", "includeme", "register"]
__version__ = "0.1.0"
