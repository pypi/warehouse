# SPDX-License-Identifier: Apache-2.0

import pretend

from tests.common.db.accounts import UserFactory
from warehouse.accounts.utils import UserContext
from warehouse.utils.security_policy import principals_for


def test_user_context_principals(db_request):
    user = UserFactory.create()
    assert principals_for(
        UserContext(user=user, macaroon=pretend.stub())
    ) == principals_for(user)
