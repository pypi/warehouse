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

import requests
import sentry_sdk
import wtforms

from warehouse import forms
from warehouse.i18n import localize as _

_VALID_GITHUB_REPO = re.compile(r"^[a-zA-Z0-9-_.]+$")
_VALID_GITHUB_OWNER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$")


class GitHubProviderForm(forms.Form):
    __params__ = ["owner", "repository", "workflow_filename"]

    owner = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(
                message=_("Specify GitHub repository owner (username or organization)"),
            ),
        ]
    )

    repository = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(message=_("Specify repository name")),
            wtforms.validators.Regexp(
                _VALID_GITHUB_REPO, message=_("Invalid repository name")
            ),
        ]
    )

    workflow_filename = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(message=_("Specify workflow filename"))
        ]
    )

    def __init__(self, *args, api_token, **kwargs):
        super().__init__(*args, **kwargs)
        self._api_token = api_token

    def _headers_auth(self):
        if not self._api_token:
            return {}
        return {"Authorization": f"token {self._api_token}"}

    def _lookup_owner(self, owner):
        # To actually validate the owner, we ask GitHub's API about them.
        # We can't do this for the repository, since it might be private.
        try:
            response = requests.get(
                f"https://api.github.com/users/{owner}",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    **self._headers_auth(),
                },
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.HTTPError:
            if response.status_code == 404:
                raise wtforms.validators.ValidationError(
                    _("Unknown GitHub user or organization.")
                )
            if response.status_code == 403:
                # GitHub's API uses 403 to signal rate limiting, and returns a JSON
                # blob explaining the reason.
                sentry_sdk.capture_message(
                    "Exceeded GitHub rate limit for user lookups. "
                    f"Reason: {response.json()}"
                )
                raise wtforms.validators.ValidationError(
                    _(
                        "GitHub has rate-limited this action. "
                        "Try again in a few minutes."
                    )
                )
            else:
                sentry_sdk.capture_message(
                    f"Unexpected error from GitHub user lookup: {response.content=}"
                )
                raise wtforms.validators.ValidationError(
                    _("Unexpected error from GitHub. Try again.")
                )
        except requests.Timeout:
            sentry_sdk.capture_message(
                "Timeout from GitHub user lookup API (possibly offline)"
            )
            raise wtforms.validators.ValidationError(
                _("Unexpected timeout from GitHub. Try again in a few minutes.")
            )

        return response.json()

    def validate_owner(self, field):
        owner = field.data

        # We pre-filter owners with a regex, to avoid loading GitHub's API
        # with usernames/org names that will never be valid.
        if not _VALID_GITHUB_OWNER.match(owner):
            raise wtforms.validators.ValidationError(
                _("Invalid GitHub user or organization name.")
            )

        owner_info = self._lookup_owner(owner)

        # NOTE: Use the normalized owner name as provided by GitHub.
        self.normalized_owner = owner_info["login"]
        self.owner_id = owner_info["id"]

    def validate_workflow_filename(self, field):
        workflow_filename = field.data

        if not (
            workflow_filename.endswith(".yml") or workflow_filename.endswith(".yaml")
        ):
            raise wtforms.validators.ValidationError(
                _("Workflow name must end with .yml or .yaml")
            )

        if "/" in workflow_filename:
            raise wtforms.validators.ValidationError(
                _("Workflow filename must be a filename only, without directories")
            )


class DeleteProviderForm(forms.Form):
    __params__ = ["provider_id"]

    provider_id = wtforms.StringField(
        validators=[
            wtforms.validators.UUID(message=_("Provider must be specified by ID"))
        ]
    )
