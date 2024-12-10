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

from warehouse.integrations.secrets import utils

# Separate for use in tests
_github_origin = utils.DisclosureOrigin(
    name="GitHub",
    key_id_header="GITHUB-PUBLIC-KEY-IDENTIFIER",
    signature_header="GITHUB-PUBLIC-KEY-SIGNATURE",
    verification_url="https://api.github.com/meta/public_keys/token_scanning",
    api_token="github.token",
)
_depsdev_origin = utils.DisclosureOrigin(
    name="Deps.dev",
    key_id_header="GOSST-PUBLIC-KEY-IDENTIFIER",
    signature_header="GOSST-PUBLIC-KEY-SIGNATURE",
    verification_url=(
        "https://storage.googleapis.com/depsdev-gcp-public-keys/secret_scanning"
    ),
)

origins = [_github_origin, _depsdev_origin]
