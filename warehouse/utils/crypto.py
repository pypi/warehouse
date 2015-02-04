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
    BadSignature, Signer as _Signer, TimestampSigner as _TimestampSigner,
)


__all__ = ["BadSignature", "Signer", "TimestampSigner", "random_token"]


def random_token(_urandom=os.urandom):
    token = base64.urlsafe_b64encode(_urandom(32)).rstrip(b"=")
    return token.decode("utf8")


class Signer(_Signer):

    default_digest_method = hashlib.sha512
    default_key_derivation = "hmac"


class TimestampSigner(_TimestampSigner):

    default_digest_method = hashlib.sha512
    default_key_derivation = "hmac"
