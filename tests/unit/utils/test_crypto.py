# SPDX-License-Identifier: Apache-2.0

import os

from warehouse.utils.crypto import random_token


def test_random_token(mocker):
    random = mocker.patch.object(
        os, "urandom", autospec=True, side_effect=lambda n: b"a" * n
    )

    assert random_token() == "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE"
    random.assert_called_once_with(32)
