# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib
import os

from itsdangerous import (
    BadData,
    BadSignature,
    SignatureExpired,
    Signer as _Signer,
    TimestampSigner as _TimestampSigner,
    URLSafeTimedSerializer as _URLSafeTimedSerializer,
)

__all__ = [
    "BadData",
    "BadSignature",
    "Signer",
    "SignatureExpired",
    "TimestampSigner",
    "URLSafeTimedSerializer",
    "random_token",
]


def random_token() -> str:
    token = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=")
    return token.decode("utf8")


class Signer(_Signer):
    default_digest_method = hashlib.sha512
    default_key_derivation = "hmac"


class TimestampSigner(_TimestampSigner):
    default_digest_method = hashlib.sha512
    default_key_derivation = "hmac"


class URLSafeTimedSerializer(_URLSafeTimedSerializer):
    default_signer = TimestampSigner
