# SPDX-License-Identifier: Apache-2.0

import re

from collections.abc import Callable
from typing import Any, TypedDict

import requests
import sentry_sdk
import wtforms

from warehouse.i18n import localize as _
from warehouse.oidc.forms._core import PendingPublisherMixin

_VALID_PROJECT_NAME = re.compile(r"^[.a-zA-Z0-9-]{3,40}$")
_DOUBLE_DASHES = re.compile(r"--+")

_ACTIVESTATE_GRAPHQL_API_URL = "https://platform.activestate.com/graphql/v1/graphql"
_GRAPHQL_GET_ORGANIZATION = "query($orgname: String) {organizations(where: {display_name: {_eq: $orgname}}) {added}}"  # noqa: E501
_GRAPHQL_GET_ACTOR = (
    "query($username: String) {users(where: {username: {_eq: $username}}) {user_id}}"
)


class UserResponse(TypedDict):
    user_id: str


class GqlResponse(TypedDict):
    data: dict[str, Any]
    errors: list[dict[str, Any]]


def _no_double_dashes(_form: wtforms.Form, field: wtforms.Field) -> None:
    if _DOUBLE_DASHES.search(field.data):
        raise wtforms.validators.ValidationError(
            _("Double dashes are not allowed in the name")
        )


def _no_leading_or_trailing_dashes(_form: wtforms.Form, field: wtforms.Field) -> None:
    if field.data.startswith("-") or field.data.endswith("-"):
        raise wtforms.validators.ValidationError(
            _("Leading or trailing dashes are not allowed in the name")
        )


def _activestate_gql_api_call(
    query: str,
    variables: dict[str, str],
    response_handler: Callable[[GqlResponse], Any],
) -> Any:
    try:
        response = requests.post(
            _ACTIVESTATE_GRAPHQL_API_URL,
            json={
                "query": query,
                "variables": variables,
            },
            timeout=5,
        )
        if response.status_code == 404:
            sentry_sdk.capture_message(
                f"Unexpected {response.status_code} error "
                f"from ActiveState API: {response.content!r}"
            )
            raise wtforms.validators.ValidationError(
                _("Unexpected error from ActiveState. Try again in a few minutes")
            )
        elif response.status_code >= 400:
            sentry_sdk.capture_message(
                f"Unexpected {response.status_code} error "
                f"from ActiveState API: {response.content!r}"
            )
            raise wtforms.validators.ValidationError(
                _("Unexpected error from ActiveState. Try again")
            )
    except (requests.Timeout, requests.ConnectionError):
        sentry_sdk.capture_message("Connection error from ActiveState API")
        raise wtforms.validators.ValidationError(
            _("Unexpected error from ActiveState. Try again in a few minutes")
        )
    # Graphql reports it's errors within the body of the 200 response
    try:
        response_json = response.json()
        errors = response_json.get("errors")
        if errors:
            sentry_sdk.capture_message(
                f"Unexpected error from ActiveState API: {errors}"
            )
            raise wtforms.validators.ValidationError(
                _("Unexpected error from ActiveState. Try again")
            )

        return response_handler(response_json)
    except requests.exceptions.JSONDecodeError:
        sentry_sdk.capture_message(
            f"Unexpected error from ActiveState API: {response.content!r}"
        )
        raise wtforms.validators.ValidationError(
            _("Unexpected error from ActiveState. Try again")
        )


class ActiveStatePublisherBase(wtforms.Form):
    __params__ = ["organization", "project", "actor"]

    organization = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify ActiveState organization name"),
            ),
        ]
    )

    project = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify ActiveState project name")
            ),
            wtforms.validators.Regexp(
                _VALID_PROJECT_NAME,
                message=_("Invalid ActiveState project name"),
            ),
            _no_double_dashes,
            _no_leading_or_trailing_dashes,
        ]
    )

    actor = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=("Specify the ActiveState actor username")
            ),
        ]
    )

    def _lookup_organization(self, org_url_name: str) -> None:
        """Make gql API call to the ActiveState API to check if the organization
        exists"""

        def process_org_response(response: GqlResponse) -> None:
            data = response.get("data")
            if data and not data.get("organizations"):
                raise wtforms.validators.ValidationError(
                    _("ActiveState organization not found")
                )

        return _activestate_gql_api_call(
            _GRAPHQL_GET_ORGANIZATION, {"orgname": org_url_name}, process_org_response
        )

    def validate_organization(self, field: wtforms.Field) -> None:
        self._lookup_organization(field.data)

    def _lookup_actor(self, actor: str) -> UserResponse:
        """Make gql API call to the ActiveState API to check if the actor/username
        exists and return the associated user id"""

        def process_actor_response(response: GqlResponse) -> UserResponse:
            users = response.get("data", {}).get("users", [])
            if users:
                return users[0]
            else:
                raise wtforms.validators.ValidationError(
                    _("ActiveState actor not found")
                )

        return _activestate_gql_api_call(
            _GRAPHQL_GET_ACTOR, {"username": actor}, process_actor_response
        )

    def validate_actor(self, field: wtforms.Field) -> None:
        actor = field.data

        actor_info = self._lookup_actor(actor)

        self.actor_id = actor_info["user_id"]


class PendingActiveStatePublisherForm(ActiveStatePublisherBase, PendingPublisherMixin):
    __params__ = ActiveStatePublisherBase.__params__ + ["project_name"]

    def __init__(self, *args, route_url, check_project_name, user, **kwargs):
        super().__init__(*args, **kwargs)
        self._route_url = route_url
        self._check_project_name = check_project_name
        self._user = user

    @property
    def provider(self) -> str:
        return "activestate"


class ActiveStatePublisherForm(ActiveStatePublisherBase):
    pass
