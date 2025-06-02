# SPDX-License-Identifier: Apache-2.0

import os

import pretend

from warehouse.utils.crypto import random_token


def test_random_token(monkeypatch):
    random = pretend.call_recorder(lambda n: b"a" * n)
    monkeypatch.setattr(os, "urandom", random)

    assert random_token() == "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE"
    assert random.calls == [pretend.call(32)]
