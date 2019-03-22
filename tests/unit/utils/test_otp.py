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

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.twofactor.totp import TOTP
from cryptography.hazmat.primitives.hashes import SHA1

from warehouse.utils.otp import (
    TOTP_LENGTH,
    TOTP_INTERVAL,
    generate_totp_secret,
    generate_totp_provisioning_uri,
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


def test_verify_totp_success():
    secret = generate_totp_secret()
    totp = TOTP(secret, TOTP_LENGTH, SHA1(), TOTP_INTERVAL, backend=default_backend())
    value = totp.generate(time.time())
    assert verify_totp(secret, value)


def test_verify_totp_success_negative_skew():
    secret = generate_totp_secret()
    totp = TOTP(secret, TOTP_LENGTH, SHA1(), TOTP_INTERVAL, backend=default_backend())
    value = totp.generate(time.time() - 20)
    assert verify_totp(secret, value)


def test_verify_totp_success_positive_skew():
    secret = generate_totp_secret()
    totp = TOTP(secret, TOTP_LENGTH, SHA1(), TOTP_INTERVAL, backend=default_backend())
    value = totp.generate(time.time() + 20)
    assert verify_totp(secret, value)


def test_verify_totp_failure():
    secret = generate_totp_secret()
    totp = TOTP(secret, TOTP_LENGTH, SHA1(), TOTP_INTERVAL, backend=default_backend())
    value = totp.generate(time.time() + 60)
    assert not verify_totp(secret, value)
