# SPDX-License-Identifier: Apache-2.0

import re
import time

from base64 import b32decode
from urllib.parse import parse_qsl

import pytest

from cryptography.hazmat.primitives.hashes import SHA1
from cryptography.hazmat.primitives.twofactor.totp import TOTP
from urllib3.util import parse_url

from warehouse.utils import otp


def test_generate_totp_secret():
    secret = otp.generate_totp_secret()

    # secret should be bytes
    assert type(secret) is bytes

    # secret should be 20 bytes long, i.e. 160 bits
    assert len(secret) == 20


def test_generate_totp_provisioning_uri():
    """
    The URI follows the Key URI Format that authenticator apps parse.

    See: https://github.com/google/google-authenticator/wiki/Key-Uri-Format
    """
    secret = otp.generate_totp_secret()
    username = "pony"
    issuer_name = "pypi.org"
    uri = otp.generate_totp_provisioning_uri(secret, username, issuer_name=issuer_name)

    parsed = parse_url(uri)

    assert parsed.scheme == "otpauth"
    assert parsed.netloc == "totp"
    assert parsed.path == f"/{issuer_name}:{username}"

    query = dict(parse_qsl(parsed.query))

    assert query["digits"] == "6"
    assert query["algorithm"] == "SHA1"
    assert query["issuer"] == issuer_name
    assert query["period"] == "30"
    # A 160-bit secret encodes to base32 with no padding, which the format
    # asks for; `cryptography` does not strip padding for other lengths.
    assert re.fullmatch(r"[A-Z2-7]+", query["secret"])
    assert b32decode(query["secret"]) == secret


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (59, "287082"),
        (1111111109, "081804"),
        (1111111111, "050471"),
        (1234567890, "005924"),
        (2000000000, "279037"),
        (20000000000, "353130"),
    ],
)
def test_totp_rfc6238_test_vectors(timestamp, expected):
    """
    The SHA1 test vectors from RFC 6238, truncated to our 6 digits.

    See: https://datatracker.ietf.org/doc/html/rfc6238#appendix-B
    """
    totp = otp._get_totp(b"12345678901234567890")
    assert totp.generate(timestamp).decode() == expected


@pytest.mark.parametrize("skew", [0, -20, 20])
def test_verify_totp_success(skew):
    secret = otp.generate_totp_secret()
    totp = TOTP(secret, otp.TOTP_LENGTH, SHA1(), otp.TOTP_INTERVAL)
    value = totp.generate(time.time() + skew)
    assert otp.verify_totp(secret, value)


@pytest.mark.parametrize("skew", [-60, 60])
def test_verify_totp_failure(skew):
    secret = otp.generate_totp_secret()
    totp = TOTP(secret, otp.TOTP_LENGTH, SHA1(), otp.TOTP_INTERVAL)
    value = totp.generate(time.time() + skew)
    with pytest.raises(otp.OutOfSyncTOTPError):
        otp.verify_totp(secret, value)
