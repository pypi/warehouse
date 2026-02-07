# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.integrations.secrets import utils


@pytest.fixture
def someorigin():
    return utils.DisclosureOrigin(
        name="SomeOrigin",
        key_id_header="SOME_KEY_ID_HEADER",
        signature_header="SOME_SIGNATURE_HEADER",
        verification_url="https://some.verification.url",
    )
