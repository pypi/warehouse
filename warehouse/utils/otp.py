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

import os
import time

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.hashes import SHA1
from cryptography.hazmat.primitives.twofactor import InvalidToken
from cryptography.hazmat.primitives.twofactor.totp import TOTP

TOTP_LENGTH = 6
TOTP_INTERVAL = 30


def _get_totp(secret):
    """
    Returns a TOTP object for device provisioning and OTP validation.

    The TOTP object is instantiated with the default OTP parameters,
    per RFC6238:
        * SHA1 digest
        * 6-digit code
        * 30-second interval
    """
    return TOTP(secret, TOTP_LENGTH, SHA1(), TOTP_INTERVAL, backend=default_backend())


def generate_totp_secret():
    """
    Generates a secret for time-based OTP.

    The default secret length is 160 bits, as per RFC4226:
    https://tools.ietf.org/html/rfc4226#section-4
    """
    return os.urandom(20)


def generate_totp_provisioning_uri(secret, username, issuer_name):
    """
    Generates a URL to be presented as a QR-code for time-based OTP.
    """
    totp = _get_totp(secret)
    return totp.get_provisioning_uri(username, issuer_name)


def _verify_totp_time(totp, value, time):
    """
    Verifies an OTP value and time against the given TOTP object.
    """
    try:
        totp.verify(value, time)
        return True
    except InvalidToken:
        return False


def verify_totp(secret, value):
    """
    Verifies a given TOTP-secret and value for the
    current time +/- 1 counter interval.

    This minimizes issues caused by clock differences and latency,
    provides a better UX, and also improves accessibility
    in cases where typing speed is limited.
    """
    totp = _get_totp(secret)
    now = time.time()
    return (
        _verify_totp_time(totp, value, now)
        or _verify_totp_time(totp, value, now - TOTP_INTERVAL)
        or _verify_totp_time(totp, value, now + TOTP_INTERVAL)
    )
