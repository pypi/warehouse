# SPDX-License-Identifier: Apache-2.0

from warehouse.api.maintainer._utils import ApiKeyContext

from ....common.db.maintainer_api import ApiKeyFactory


def test_api_key_context_principals(db_request):
    api_key = ApiKeyFactory.create()
    context = ApiKeyContext(user=api_key.user, api_key=api_key)

    assert context.__principals__() == api_key.user.__principals__()
