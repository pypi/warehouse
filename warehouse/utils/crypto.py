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


def random_token():
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
