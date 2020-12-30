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
import binascii


def vault_ed25519_pubkey_for_tuf(pubkey):
    # NOTE: unit test this against secure-systems-lib schemas.
    pubkey = base64.b64decode(pubkey)
    return {
        "keytype": "ed25519",
        "schema": "ed25519",
        "keyid_hash_algorithms": "sha256",
        "keyval": {
            "public": binascii.hexlify(pubkey),
            "private": "",
        }
    }
