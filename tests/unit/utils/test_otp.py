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

import base64

import pyotp

from warehouse.utils.otp import (
    generate_totp_secret,
    generate_totp_provisioning_uri,
    verify_totp,
)


def test_generate_totp_secret():
    secret = generate_totp_secret()

    # ensure it decodes as base32 and is 160 bits long
    assert len(base64.b32decode(secret)) == 20


def test_generate_totp_provisioning_uri():
    secret = "F" * 32
    username = "pony"
    issuer_name = "pypi.org"
    uri = generate_totp_provisioning_uri(secret, username, issuer_name=issuer_name)
    expected_uri = "otpauth://totp/{0}:{1}?secret={2}&issuer={3}".format(
        issuer_name, username, secret, issuer_name
    )
    assert uri == expected_uri


def test_verify_totp_success():
    secret = generate_totp_secret()
    value = pyotp.TOTP(secret).now()
    assert verify_totp(secret, value)


def test_verify_totp_failure():
    secret = generate_totp_secret()
    value = pyotp.TOTP(secret).now()
    value_plus_one = str((int(value) + 1) % (999999 + 1)).zfill(6)
    assert not verify_totp(secret, value_plus_one, valid_window=0)
