# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re

from collections.abc import Callable
from typing import Any, TypedDict

import requests
import sentry_sdk
import wtforms

from warehouse import forms
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


def _no_double_dashes(form, field):
    if _DOUBLE_DASHES.search(field.data):
        raise wtforms.validators.ValidationError(
            _("Double dashes are not allowed in the name")
        )


def _no_leading_or_trailing_dashes(form, field):
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


class ActiveStatePublisherBase(forms.Form):
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

    def validate_organization(self, field):
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

    def validate_actor(self, field):
        actor = field.data

        actor_info = self._lookup_actor(actor)

        self.actor_id = actor_info["user_id"]


class PendingActiveStatePublisherForm(ActiveStatePublisherBase, PendingPublisherMixin):
    __params__ = ActiveStatePublisherBase.__params__ + ["project_name"]

    def __init__(self, *args, project_factory, **kwargs):
        super().__init__(*args, **kwargs)
        self._project_factory = project_factory


class ActiveStatePublisherForm(ActiveStatePublisherBase):
    pass
