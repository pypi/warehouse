# SPDX-License-Identifier: Apache-2.0

from warehouse.api.maintainer._scopes import (
    PERMISSION_SCOPES,
    SCOPE_PERMISSIONS,
    ApiKeyScope,
)
from warehouse.utils.security_policy import (
    PERMISSION_AUTH_METHODS,
    AuthenticationMethod,
)


def test_every_scope_has_a_permission():
    assert set(SCOPE_PERMISSIONS) == set(ApiKeyScope)


def test_permission_scopes_need_api_key_auth():
    """Every permission with a scope must also be grantable by an API key."""
    for permission in PERMISSION_SCOPES:
        assert AuthenticationMethod.API_KEY in PERMISSION_AUTH_METHODS[permission]
