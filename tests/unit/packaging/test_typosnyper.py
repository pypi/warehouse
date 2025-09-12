# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.packaging.typosnyper import typo_check_name


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("numpy", None),  # Pass, no typos, exists
        ("NuMpy", None),  # Pass, same as `numpy` after canonicalization
        ("nuumpy", ("repeated_characters", "numpy")),
        ("reequests", ("repeated_characters", "requests")),
        ("sphnx", ("omitted_characters", "sphinx")),
        ("python-dteutil", ("omitted_characters", "python-dateutil")),
        ("pythondateutil", ("omitted_characters", "python-dateutil")),
        ("jinj2a", ("swapped_characters", "jinja2")),
        ("dateutil-python", ("swapped_words", "python-dateutil")),
        ("numpi", ("common_typos", "numpy")),
        ("requestz", ("common_typos", "requests")),
        ("python-dateutil", None),  # Pass, swapped_words same as original
    ],
)
def test_typo_check_name(name, expected):
    # Set known entries corpus entries for testing
    test_names_corpus = {
        "numpy",
        "requests",
        "sphinx",
        "beautifulsoup4",
        "jinja2",
        "python-dateutil",
    }

    assert typo_check_name(name, corpus=test_names_corpus) == expected
