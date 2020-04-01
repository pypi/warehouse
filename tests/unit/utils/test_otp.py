# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time

from base64 import b32encode
from urllib.parse import parse_qsl, urlparse

import pytest

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.hashes import SHA1
from cryptography.hazmat.primitives.twofactor.totp import TOTP

from warehouse.utils.otp import (
    TOTP_INTERVAL,
    TOTP_LENGTH,
    generate_totp_provisioning_uri,
    generate_totp_secret,
    verify_totp,
)


def test_generate_totp_secret():
    secret = generate_totp_secret()

    # secret should be bytes
    assert type(secret) == bytes

    # secret should be 20 bytes long, i.e. 160 bits
    assert len(secret) == 20


def test_generate_totp_provisioning_uri():
    secret = b"F" * 32
    username = "pony"
    issuer_name = "pypi.org"
    uri = generate_totp_provisioning_uri(secret, username, issuer_name=issuer_name)

    parsed = urlparse(uri)

    assert parsed.scheme == "otpauth"
    assert parsed.netloc == "totp"
    assert parsed.path == f"/{issuer_name}:{username}"

    query = parse_qsl(parsed.query)

    assert ("digits", "6") in query
    assert ("secret", b32encode(secret).decode()) in query
    assert ("algorithm", "SHA1") in query
    assert ("issuer", issuer_name) in query
    assert ("period", "30") in query


@pytest.mark.parametrize("skew", [0, -20, 20])
def test_verify_totp_success(skew):
    secret = generate_totp_secret()
    totp = TOTP(secret, TOTP_LENGTH, SHA1(), TOTP_INTERVAL, backend=default_backend())
    value = totp.generate(time.time() + skew)
    assert verify_totp(secret, value)


@pytest.mark.parametrize("skew", [-60, 60])
def test_verify_totp_failure(skew):
    secret = generate_totp_secret()
    totp = TOTP(secret, TOTP_LENGTH, SHA1(), TOTP_INTERVAL, backend=default_backend())
    value = totp.generate(time.time() + skew)
    assert not verify_totp(secret, value)
