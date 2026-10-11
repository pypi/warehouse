# SPDX-License-Identifier: Apache-2.0

from unittest import mock

import pytest

from tests import conftest


def test_guard_mock_sentinels_reports_and_restores_mutations():
    first = mock.sentinel.guard_test_first
    first.leaked = object()

    guard = conftest.guard_mock_sentinels.__wrapped__()
    next(guard)

    second = mock.sentinel.guard_test_second
    second.also_leaked = object()

    with pytest.raises(AssertionError) as exc_info:
        next(guard)

    assert "mock.sentinel.guard_test_first" in str(exc_info.value)
    assert "mock.sentinel.guard_test_second" in str(exc_info.value)
    assert vars(first) == {"name": "guard_test_first"}
    assert vars(second) == {"name": "guard_test_second"}
