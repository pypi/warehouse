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

import pyotp


def generate_totp_secret():
    """
    Generates a secret for time-based OTP.

    The default secret length is 160 bits, as per RFC4226:
    https://tools.ietf.org/html/rfc4226#section-4

    Given the base32 encoding, it is represented as a 32-character string, i.e.:
    5 bits per character * 32 characters = 160 bits.

    TODO:
    consider using os.urandom(); this, however, is likely to cause
    compatibility issues unless base32 vocabulary is used.
    """
    return pyotp.random_base32(length=32)


def generate_totp_provisioning_uri(secret, username, issuer_name=None):
    """
    Generates a URL to be presented as a QR-code for time-based OTP.

    This function doesn't accept any custom TOTP parameters, since these are
    not supported by many OTP applications. Defaults are as per RFC6238:
        * SHA1 digest
        * 6-digit code
        * 30-second interval
    """
    return pyotp.TOTP(secret).provisioning_uri(username, issuer_name=issuer_name)


def verify_totp(secret, value, valid_window=1):
    """
    Verifies a given TOTP-secret and value.

    The *valid_window* argument value is intentionally chosen to be non-zero
    (while the library defaults to 0). This provides a better UX, working around
    a range issues:
        * typing a code too close to an interval end;
        * user device clock synchronization issues;
        * poor network connection quality.
    This is also an accessibility feature that accounts for cases when typing
    speed may be limited.
    """
    return pyotp.TOTP(secret).verify(value, valid_window=valid_window)
