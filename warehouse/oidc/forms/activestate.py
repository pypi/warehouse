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

from typing import TypedDict

import requests
import sentry_sdk
import wtforms

from warehouse import forms
from warehouse.i18n import localize as _
from warehouse.utils.project import PROJECT_NAME_RE

_VALID_ORG_URL_NAME_AND_ACTOR_NAME = re.compile(r"^[a-zA-Z0-9-]{3,40}$")
_VALID_PROJECT_NAME = re.compile(r"^[.a-zA-Z0-9-]{3,40}$")
_DOUBLE_DADHES = re.compile(r"--+")

ACTIVESTATE_GRAPHQL_API_URL = "https://platform.activestate.com/graphql/v1/graphql"
GRAPHQL_GET_ORGANIZATION = "query($orgname: String) {organizations(where: {display_name: {_eq: $orgname}}) {added}}"  # noqa
GRAPHQL_GET_ACTOR = (
    "query($username: String) {users(where: {username: {_eq: $username}}) {user_id}}"
)
TIMEOUT = 5


class UserResponse(TypedDict):
    user_id: str


def _no_double_dashes(form, field):
    if _DOUBLE_DADHES.search(field.data):
        raise wtforms.validators.ValidationError(
            _("Double dashes are not allowed in the name")
        )


def _no_leading_or_trailing_dashes(form, field):
    if field.data.startswith("-") or field.data.endswith("-"):
        raise wtforms.validators.ValidationError(
            _("Leading or trailing dashes are not allowed in the name")
        )


class ActiveStatePublisherBase(forms.Form):
    __params__ = ["organization", "project", "actor"]

    organization = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify ActiveState organization name"),
            ),
            wtforms.validators.Regexp(
                _VALID_ORG_URL_NAME_AND_ACTOR_NAME,
                message=_("Invalid ActiveState organization name"),
            ),
            _no_double_dashes,
            _no_leading_or_trailing_dashes,
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
            wtforms.validators.Regexp(
                _VALID_ORG_URL_NAME_AND_ACTOR_NAME,
                message=("Invalid ActiveState username"),
            ),
            _no_double_dashes,
            _no_leading_or_trailing_dashes,
        ]
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _lookup_organization(self, org_url_name: str) -> None:
        """Make gql API call to the ActiveState API to check if the organization
        exists"""
        try:
            response = requests.post(
                f"{ACTIVESTATE_GRAPHQL_API_URL}",
                json={
                    "query": GRAPHQL_GET_ORGANIZATION,
                    "variables": {"orgname": org_url_name},
                },
                timeout=TIMEOUT,
            )
            response.raise_for_status()
        except requests.HTTPError:
            sentry_sdk.capture_message(
                f"Unexpected error from ActiveState organization lookup: {response.content!r}"  # noqa
            )
            raise wtforms.validators.ValidationError(
                _("Unexpected error from ActiveState. Try again")
            )
        except requests.ConnectionError:
            sentry_sdk.capture_message(
                "Connection error from ActiveState organization lookup API (possibly offline)"  # noqa
            )
            raise wtforms.validators.ValidationError(
                _(
                    "Unexpected connection error from ActiveState. "
                    "Try again in a few minutes"
                )
            )
        except requests.Timeout:
            sentry_sdk.capture_message(
                "Timeout from ActiveState organization lookup API (possibly offline)"
            )
            raise wtforms.validators.ValidationError(
                _("Unexpected timeout from ActiveState. Try again in a few minutes")
            )
        # Graphql reports it's errors within the body of the 200 response
        try:
            response_json = response.json()
            errors = response_json.get("errors")
            if errors:
                sentry_sdk.capture_message(
                    f"Unexpected error from ActiveState organization lookup: {errors}"  # noqa
                )
                raise wtforms.validators.ValidationError(
                    _("Unexpected error from ActiveState. Try again")
                )

            if response_json.get("data") and not response_json.get("data").get(
                "organizations"
            ):
                raise wtforms.validators.ValidationError(
                    _("ActiveState organization not found")
                )
        except requests.exceptions.JSONDecodeError:
            sentry_sdk.capture_message(
                f"Unexpected error from ActiveState organization lookup: {response.content!r}"  # noqa
            )
            raise wtforms.validators.ValidationError(
                _("Unexpected error from ActiveState. Try again")
            )

    def validate_organization(self, field):
        self._lookup_organization(field.data)

    def _lookup_actor(self, actor: str) -> UserResponse:
        """Make gql API call to the ActiveState API to check if the actor/username
        exists and return the associated user id"""
        try:
            response = requests.post(
                f"{ACTIVESTATE_GRAPHQL_API_URL}",
                json={
                    "query": GRAPHQL_GET_ACTOR,
                    "variables": {"username": actor},
                },
                timeout=TIMEOUT,
            )
            response.raise_for_status()
        except requests.HTTPError:
            sentry_sdk.capture_message(
                f"Unexpected error from ActiveState actor lookup: {response.content!r}"
            )
            raise wtforms.validators.ValidationError(
                _("Unexpected error from ActiveState. Try again")
            )
        except requests.ConnectionError:
            sentry_sdk.capture_message(
                "Connection error from ActiveState actor lookup API (possibly offline)"
            )
            raise wtforms.validators.ValidationError(
                _(
                    "Unexpected connection error from ActiveState. "
                    "Try again in a few minutes"
                )
            )
        except requests.Timeout:
            sentry_sdk.capture_message(
                "Timeout from ActiveState actor lookup API (possibly offline)"
            )
            raise wtforms.validators.ValidationError(
                _("Unexpected timeout from ActiveState. Try again in a few minutes")
            )
        # Graphql reports it's errors within the body of the 200 response
        try:
            response_json = response.json()
            errors = response_json.get("errors")
            if errors:
                sentry_sdk.capture_message(
                    f"Unexpected error from ActiveState actor lookup: {errors}"  # noqa
                )
                raise wtforms.validators.ValidationError(
                    _("Unexpected error from ActiveState. Try again")
                )
            data = response_json.get("data")
            if data and data.get("users"):
                return data["users"][0]
            else:
                raise wtforms.validators.ValidationError(
                    _("ActiveState actor not found")
                )
        except requests.exceptions.JSONDecodeError:
            sentry_sdk.capture_message(
                f"Unexpected error from ActiveState actor lookup: {response.content!r}"
            )
            raise wtforms.validators.ValidationError(
                _("Unexpected error from ActiveState. Try again")
            )

    def validate_actor(self, field):
        actor = field.data

        actor_info = self._lookup_actor(actor)

        self.actor_id = actor_info["user_id"]


class PendingActiveStatePublisherForm(ActiveStatePublisherBase):
    __params__ = ActiveStatePublisherBase.__params__ + ["project_name"]

    project_name = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify project name")),
            wtforms.validators.Regexp(
                PROJECT_NAME_RE, message=_("Invalid project name")
            ),
        ]
    )

    def __init__(self, *args, project_factory, **kwargs):
        super().__init__(*args, **kwargs)
        self._project_factory = project_factory

    def validate_project_name(self, field):
        project_name = field.data

        if project_name in self._project_factory:
            raise wtforms.validators.ValidationError(
                _("This project name is already in use")
            )


class ActiveStatePublisherForm(ActiveStatePublisherBase):
    pass
