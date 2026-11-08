# SPDX-License-Identifier: Apache-2.0

import datetime as dt

from http import HTTPStatus

from warehouse.api.maintainer import ApiKeyScope, generate_api_key

from ...common.db.accounts import UserFactory
from ...common.db.maintainer_api import ApiKeyFactory

DANGER_JSON = "application/vnd.pypi.api-v0-danger+json"


def _admin_key(expires, scopes=(ApiKeyScope.TestEcho, ApiKeyScope.TestTokenExchange)):
    raw_key = generate_api_key()
    api_key = ApiKeyFactory.create(
        user=UserFactory.create(
            is_superuser=True, clear_pwd="password", with_verified_primary_email=True
        ),
        raw_key=raw_key,
        scopes=[scope.value for scope in scopes],
        expires=expires,
    )
    return raw_key, api_key


def test_expired_api_key(webtest):
    raw_key, _ = _admin_key(dt.datetime(2026, 1, 1))

    resp = webtest.get(
        "/danger-api/echo",
        headers={"Authorization": f"Bearer {raw_key}", "Accept": DANGER_JSON},
        status=HTTPStatus.UNAUTHORIZED,
    )

    assert resp.content_type == "application/problem+json"
    assert resp.json["detail"] == "Maintainer API key expired at 2026-01-01T00:00:00Z"
    assert 'error="invalid_token"' in resp.headers["WWW-Authenticate"]
