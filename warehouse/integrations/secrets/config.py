# SPDX-License-Identifier: Apache-2.0

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
