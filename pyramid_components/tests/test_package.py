# SPDX-License-Identifier: Apache-2.0
import pyramid_components as pc


def test_package_is_importable():
    """__version__ is the single version source (pyproject reads it via dynamic)."""
    assert pc.__version__
