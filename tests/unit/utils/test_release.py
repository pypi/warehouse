# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.utils.release import strip_keywords


@pytest.mark.parametrize(
    ("keyword_input", "expected"),
    [
        ([], []),
        ([""], []),
        (["foo", "bar"], ["foo", "bar"]),
        (["foo", "bar baz", ""], ["foo", "bar baz"]),
        (["foo", "bar", "baz", "", ""], ["foo", "bar", "baz"]),
    ],
)
def test_split_and_strip_keywords(keyword_input, expected):
    assert strip_keywords(keyword_input) == expected
