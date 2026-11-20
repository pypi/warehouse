# SPDX-License-Identifier: Apache-2.0

import datetime as dt
import uuid

import pytest

from pyramid.httpexceptions import HTTPSeeOther
from webob.multidict import MultiDict

from warehouse.api.maintainer import MAX_ACTIVE_API_KEYS, ApiKeyScope, hash_api_key
from warehouse.events.tags import EventTag
from warehouse.manage.forms import CreateApiKeyForm
from warehouse.manage.views import api_keys as views
from warehouse.utils import now

from ....common.db.accounts import UserFactory
from ....common.db.maintainer_api import ApiKeyFactory


@pytest.fixture
def admin_request(db_request, mocker):
    db_request.method = "POST"
    db_request.POST = MultiDict()
    db_request.user = UserFactory.create(is_superuser=True)
    mocker.patch.object(
        db_request, "route_path", autospec=True, side_effect=lambda n: f"/{n}/"
    )
    mocker.spy(db_request.session, "flash")
    mocker.spy(db_request.user, "record_event")
    return db_request


class TestManageApiKeysViews:
    def test_manage_api_keys(self, admin_request):
        # Relative to now, so the lifetime CHECK holds whenever this runs.
        older = ApiKeyFactory.create(
            user=admin_request.user, created=now() - dt.timedelta(days=2)
        )
        newer = ApiKeyFactory.create(
            user=admin_request.user, created=now() - dt.timedelta(days=1)
        )
        ApiKeyFactory.create()  # someone else's

        result = views.ManageApiKeysViews(admin_request).manage_api_keys()

        assert result["api_keys"] == [newer, older]
        form = result["create_api_key_form"]
        assert isinstance(form, CreateApiKeyForm)
        assert [choice.value for choice in form.scopes.choices] == [
            "test:echo",
            "test:token:exchange",
        ]

    def test_manage_api_keys_hides_long_inactive(self, admin_request):
        def inactive_for(days, **kwargs):
            return ApiKeyFactory.create(
                user=admin_request.user,
                created=now() - dt.timedelta(days=days + 1),
                **kwargs,
            )

        shown = [
            inactive_for(89, revoked=now() - dt.timedelta(days=89)),
            inactive_for(89, expires=now() - dt.timedelta(days=89)),
        ]
        inactive_for(91, revoked=now() - dt.timedelta(days=91))
        inactive_for(91, expires=now() - dt.timedelta(days=91))

        result = views.ManageApiKeysViews(admin_request).manage_api_keys()

        assert set(result["api_keys"]) == set(shown)

    def test_create_api_key(self, admin_request, mocker):
        frozen = dt.datetime(2026, 11, 6, 12, 0)
        mocker.patch.object(views, "now", autospec=True, return_value=frozen)
        admin_request.POST = MultiDict(
            [
                ("name", "testing"),
                ("scopes", "test:echo"),
                ("scopes", "test:token:exchange"),
                ("expires_in_days", "7"),
            ]
        )

        result = views.ManageApiKeysViews(admin_request).create_api_key()

        api_key = result["api_key"]
        assert api_key.hashed_key == hash_api_key(result["raw_api_key"])
        assert api_key.user == admin_request.user
        assert api_key.scopes == ["test:echo", "test:token:exchange"]
        assert api_key.expires == frozen + dt.timedelta(days=7)
        assert result["api_keys"] == [api_key]
        admin_request.user.record_event.assert_called_once_with(
            tag=EventTag.Account.APIKeyAdded,
            request=admin_request,
            additional={
                "name": "testing",
                "api_key_id": str(api_key.id),
                "scopes": ["test:echo", "test:token:exchange"],
            },
        )

    def test_create_api_key_scope_not_allowed(self, admin_request, mocker):
        """A scope whose permission the user lacks is not offered."""
        mocker.patch.object(
            admin_request, "has_permission", autospec=True, return_value=False
        )
        admin_request.POST = MultiDict(
            {"name": "x", "scopes": "test:echo", "expires_in_days": "7"}
        )

        result = views.ManageApiKeysViews(admin_request).create_api_key()

        assert "raw_api_key" not in result
        form = result["create_api_key_form"]
        assert form.scopes.choices == []
        assert form.scopes.errors
        admin_request.user.record_event.assert_not_called()

    @pytest.mark.parametrize(
        "post",
        [
            pytest.param({"scopes": "test:echo", "expires_in_days": "7"}, id="name"),
            pytest.param(
                {"name": "   ", "scopes": "test:echo", "expires_in_days": "7"},
                id="blank name",
            ),
            pytest.param({"name": "x", "expires_in_days": "7"}, id="no scopes"),
            pytest.param(
                {"name": "x", "scopes": "nope", "expires_in_days": "7"},
                id="unknown scope",
            ),
            pytest.param(
                {"name": "x", "scopes": "test:echo", "expires_in_days": "366"},
                id="too long",
            ),
        ],
    )
    def test_create_api_key_invalid(self, admin_request, post):
        admin_request.POST = MultiDict({"name": "", **post})

        result = views.ManageApiKeysViews(admin_request).create_api_key()

        assert "raw_api_key" not in result
        assert result["create_api_key_form"].errors
        assert result["api_keys"] == []
        admin_request.user.record_event.assert_not_called()

    def test_create_api_key_at_limit(self, admin_request):
        ApiKeyFactory.create_batch(MAX_ACTIVE_API_KEYS, user=admin_request.user)
        admin_request.POST = MultiDict(
            {"name": "ci", "scopes": "test:echo", "expires_in_days": "7"}
        )

        result = views.ManageApiKeysViews(admin_request).create_api_key()

        assert "raw_api_key" not in result
        assert result["create_api_key_form"].name.errors == [
            (
                "You have the most active Maintainer API keys allowed. "
                "Revoke one to create another."
            )
        ]
        admin_request.user.record_event.assert_not_called()

    def test_create_api_key_name_in_use(self, admin_request):
        ApiKeyFactory.create(user=admin_request.user, name="ci")
        admin_request.POST = MultiDict(
            {"name": "ci", "scopes": "test:echo", "expires_in_days": "7"}
        )

        result = views.ManageApiKeysViews(admin_request).create_api_key()

        assert "raw_api_key" not in result
        assert result["create_api_key_form"].name.errors == ["Key name already in use"]

    def test_revoke_api_key(self, admin_request):
        api_key = ApiKeyFactory.create(
            user=admin_request.user, scopes=[ApiKeyScope.TestEcho.value]
        )
        admin_request.POST = MultiDict({"revoke_api_key_id": str(api_key.id)})

        result = views.ManageApiKeysViews(admin_request).revoke_api_key()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage.account.api-keys/"
        admin_request.db.refresh(api_key)
        assert api_key.revoked is not None
        admin_request.session.flash.assert_called_once_with(
            f"Maintainer API key {api_key.name} revoked", queue="success"
        )
        admin_request.user.record_event.assert_called_once_with(
            tag=EventTag.Account.APIKeyRevoked,
            request=admin_request,
            additional={"name": api_key.name, "api_key_id": str(api_key.id)},
        )

    @pytest.mark.parametrize(
        "make_id",
        [
            pytest.param(lambda request: "not-a-uuid", id="malformed"),
            pytest.param(lambda request: str(uuid.uuid4()), id="unknown"),
            pytest.param(
                lambda request: str(ApiKeyFactory.create().id), id="someone else's"
            ),
            pytest.param(
                lambda request: str(
                    ApiKeyFactory.create(
                        user=request.user, revoked=dt.datetime(2026, 1, 1)
                    ).id
                ),
                id="already revoked",
            ),
        ],
    )
    def test_revoke_api_key_not_found(self, admin_request, make_id):
        admin_request.POST = MultiDict({"revoke_api_key_id": make_id(admin_request)})

        result = views.ManageApiKeysViews(admin_request).revoke_api_key()

        assert isinstance(result, HTTPSeeOther)
        admin_request.session.flash.assert_called_once_with(
            "Maintainer API key not found", queue="error"
        )
        admin_request.user.record_event.assert_not_called()
