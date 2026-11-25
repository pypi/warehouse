# SPDX-License-Identifier: Apache-2.0

import datetime as dt

import jwt
import pytest

from pyramid.testing import DummySecurityPolicy

from warehouse.api.maintainer import ApiKeyContext, ApiKeyScope, _views as views

from ....common.db.accounts import UserFactory
from ....common.db.maintainer_api import ApiKeyFactory

ISSUED_AT = 1_800_000_000  # 2027-01-15T08:00:00Z


@pytest.fixture
def exchange(db_request, pyramid_config, mocker):
    """Run the exchange for a key and return the response and its claims."""
    mocker.patch.object(views.time, "time", return_value=ISSUED_AT)

    def _exchange(api_key):
        pyramid_config.set_security_policy(
            DummySecurityPolicy(
                identity=ApiKeyContext(user=api_key.user, api_key=api_key)
            )
        )
        result = views.api_token_exchange(db_request)
        claims = jwt.decode(
            result["access_token"],
            options={"verify_signature": False, "verify_exp": False},
            audience=views.SCAFFOLD_AUDIENCE,
        )
        return result, claims

    return _exchange


def _expires(seconds):
    return dt.datetime.fromtimestamp(ISSUED_AT + seconds, dt.UTC).replace(tzinfo=None)


def test_api_token_exchange(db_request, exchange):
    api_key = ApiKeyFactory.create(
        user=UserFactory.create(is_superuser=True),
        scopes=[ApiKeyScope.TestTokenExchange.value],
        expires=_expires(86400),
    )

    result, claims = exchange(api_key)

    assert db_request.response.headers["Cache-Control"] == "no-store"
    assert db_request.response.headers["Pragma"] == "no-cache"
    assert result["token_type"] == "Bearer"
    assert result["expires_in"] == views.ACCESS_TOKEN_TTL.total_seconds()
    assert jwt.get_unverified_header(result["access_token"]) == {
        "alg": "none",
        "typ": "JWT",
    }
    assert claims == {
        "iss": db_request.host_url,
        "aud": views.SCAFFOLD_AUDIENCE,
        "sub": str(api_key.user_id),
        "iat": ISSUED_AT,
        "exp": ISSUED_AT + views.ACCESS_TOKEN_TTL.total_seconds(),
        "jti": claims["jti"],
        "api_key_id": str(api_key.id),
        "scp": "test:token:exchange",
    }


def test_api_token_exchange_never_outlives_key(exchange):
    api_key = ApiKeyFactory.create(
        user=UserFactory.create(is_superuser=True), expires=_expires(60)
    )

    result, claims = exchange(api_key)

    assert result["expires_in"] == 60
    assert claims["exp"] == ISSUED_AT + 60


def test_api_token_exchange_drops_scopes_owner_lost(exchange):
    """scp lists only the scopes the owner still holds."""
    api_key = ApiKeyFactory.create(
        user=UserFactory.create(is_superuser=False),
        scopes=[scope.value for scope in ApiKeyScope],
        expires=_expires(86400),
    )

    _, claims = exchange(api_key)

    assert claims["scp"] == ""


def test_api_token_exchange_key_expired_mid_request(db_request, pyramid_config, mocker):
    """A key that expired after authentication gets no token."""
    mocker.patch.object(views.time, "time", return_value=ISSUED_AT)
    api_key = ApiKeyFactory.create(
        user=UserFactory.create(is_superuser=True), expires=_expires(0)
    )
    pyramid_config.set_security_policy(
        DummySecurityPolicy(identity=ApiKeyContext(user=api_key.user, api_key=api_key))
    )

    resp = views.api_token_exchange(db_request)

    assert resp.status_code == 401
    assert resp.json_body["detail"] == "Maintainer API key expired."
    assert 'error="invalid_token"' in resp.headers["WWW-Authenticate"]
