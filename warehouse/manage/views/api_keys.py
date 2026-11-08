# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime as dt

from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPSeeOther
from pyramid.view import view_config, view_defaults
from sqlalchemy import func, select

from warehouse.api.maintainer import (
    SCOPE_PERMISSIONS,
    ApiKey,
    ApiKeyLimitError,
    ApiKeyNameInUseError,
    IApiKeyService,
)
from warehouse.authnz import Permissions
from warehouse.config import has_root_permission
from warehouse.events.tags import EventTag
from warehouse.manage.forms import CreateApiKeyForm
from warehouse.manage.views.view_helpers import parse_uuid
from warehouse.utils import now

if TYPE_CHECKING:
    from pyramid.request import Request

# How long a revoked or expired key stays on the manage page.
INACTIVE_KEYS_SHOWN_FOR = dt.timedelta(days=90)


@view_defaults(
    route_name="manage.account.api-keys",
    renderer="warehouse:templates/manage/account/api-keys.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.AccountAPIKeys,
    has_translations=True,
    require_reauth=True,
)
class ManageApiKeysViews:
    """List, create and revoke Maintainer API keys."""

    def __init__(self, request: Request):
        self.request = request
        self.api_key_service = request.find_service(IApiKeyService, context=None)

    def _api_keys(self) -> list[ApiKey]:
        """Active keys, plus revoked or expired ones for a while after."""
        went_inactive = func.coalesce(ApiKey.revoked, ApiKey.expires)
        shown_since = now() - INACTIVE_KEYS_SHOWN_FOR
        return list(
            self.request.db.scalars(
                select(ApiKey)
                .where(
                    ApiKey.user_id == self.request.user.id, went_inactive > shown_since
                )
                .order_by(ApiKey.created.desc(), ApiKey.id.desc())
            )
        )

    def _form(self, formdata=None) -> CreateApiKeyForm:
        return CreateApiKeyForm(
            formdata,
            scopes=[
                scope
                for scope, permission in SCOPE_PERMISSIONS.items()
                if has_root_permission(self.request, permission)
            ],
        )

    @view_config(request_method="GET")
    def manage_api_keys(self) -> dict:
        return {"api_keys": self._api_keys(), "create_api_key_form": self._form()}

    @view_config(request_method="POST", request_param=["name"])
    def create_api_key(self) -> dict:
        form = self._form(self.request.POST)
        if form.validate():
            # Both are required fields, so validate() guarantees them.
            days, scopes = form.expires_in_days.data, form.scopes.data
            assert days is not None
            assert scopes is not None
            try:
                raw_key, api_key = self.api_key_service.create_api_key(
                    self.request.user,
                    form.name.data,
                    scopes,
                    now() + dt.timedelta(days=days),
                )
            except ApiKeyLimitError:
                form.name.errors = [
                    self.request._(
                        "You have the most active Maintainer API keys allowed. "
                        "Revoke one to create another."
                    )
                ]
            except ApiKeyNameInUseError:
                form.name.errors = [self.request._("Key name already in use")]
            else:
                self.request.user.record_event(
                    tag=EventTag.Account.APIKeyAdded,
                    request=self.request,
                    additional={
                        "name": api_key.name,
                        "api_key_id": str(api_key.id),
                        "scopes": api_key.scopes,
                    },
                )
                # As for API tokens, render instead of redirecting: the key
                # shows once.
                return {
                    "api_keys": self._api_keys(),
                    "create_api_key_form": self._form(),
                    "raw_api_key": raw_key,
                    "api_key": api_key,
                }
        return {"api_keys": self._api_keys(), "create_api_key_form": form}

    @view_config(request_method="POST", request_param=["revoke_api_key_id"])
    def revoke_api_key(self) -> HTTPSeeOther:
        # A malformed ID parses to None, which matches no key.
        api_key = self.request.db.scalar(
            select(ApiKey).where(
                ApiKey.id == parse_uuid(self.request.POST["revoke_api_key_id"]),
                ApiKey.user_id == self.request.user.id,
            )
        )

        if api_key is None or not self.api_key_service.revoke(api_key.id):
            self.request.session.flash(
                self.request._("Maintainer API key not found"), queue="error"
            )
        else:
            self.request.user.record_event(
                tag=EventTag.Account.APIKeyRevoked,
                request=self.request,
                additional={"name": api_key.name, "api_key_id": str(api_key.id)},
            )
            self.request.session.flash(
                self.request._(
                    "Maintainer API key ${name} revoked", mapping={"name": api_key.name}
                ),
                queue="success",
            )

        return HTTPSeeOther(self.request.route_path("manage.account.api-keys"))
