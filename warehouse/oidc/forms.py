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
from warehouse.utils.project import PROJECT_NAME_RE

_VALID_GITHUB_REPO = r"[a-zA-Z0-9-_.]+"
_VALID_GITHUB_OWNER = r"[a-zA-Z0-9][a-zA-Z0-9-]*"
_VALID_GITHUB_SLUG = re.compile(rf"^{_VALID_GITHUB_OWNER}/{_VALID_GITHUB_REPO}$")


class GitHubPublisherBase(forms.Form):
    __params__ = ["repo_slug", "workflow_filename", "environment"]

    repo_slug = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(
                message=_("Specify GitHub repo slug (in user/repo format)"),
            ),
        ]
    )

    workflow_filename = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(message=_("Specify workflow filename"))
        ]
    )

    # Environment names are not case sensitive. An environment name may not
    # exceed 255 characters and must be unique within the repository.
    # https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
    environment = wtforms.StringField(validators=[wtforms.validators.Optional()])

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
        except requests.ConnectionError:
            sentry_sdk.capture_message(
                "Connection error from GitHub user lookup API (possibly offline)"
            )
            raise wtforms.validators.ValidationError(
                _(
                    "Unexpected connection error from GitHub. "
                    "Try again in a few minutes."
                )
            )
        except requests.Timeout:
            sentry_sdk.capture_message(
                "Timeout from GitHub user lookup API (possibly offline)"
            )
            raise wtforms.validators.ValidationError(
                _("Unexpected timeout from GitHub. Try again in a few minutes.")
            )

        return response.json()

    def validate_repo_slug(self, field):
        if not _VALID_GITHUB_SLUG.match(field.data):
            raise wtforms.validators.ValidationError(
                _("Invalid repository: not in user/repo format")
            )

        # Compute DB's `repository_name` `repository_owner` from the form's `repo_slug`.
        repo_slug = field.data.split("/")
        (owner, repository) = (repo_slug[0], repo_slug[1])

        owner_info = self._lookup_owner(owner)

        # NOTE: Use the normalized owner name as provided by GitHub.
        self.normalized_owner = owner_info["login"]
        self.owner_id = owner_info["id"]
        self.repository = repository

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

    @property
    def normalized_environment(self):
        # NOTE: We explicitly do not compare `self.environment.data` to None,
        # since it might also be falsey via an empty string (or might be
        # only whitespace, which we also treat as a None case).
        return (
            self.environment.data.lower()
            if self.environment.data and not self.environment.data.isspace()
            else None
        )


class PendingGitHubPublisherForm(GitHubPublisherBase):
    __params__ = GitHubPublisherBase.__params__ + ["project_name"]

    project_name = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(message=_("Specify project name")),
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


class GitHubPublisherForm(GitHubPublisherBase):
    pass


class DeletePublisherForm(forms.Form):
    __params__ = ["publisher_id"]

    publisher_id = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(message=_("Specify a publisher ID")),
            wtforms.validators.UUID(message=_("Publisher must be specified by ID")),
        ]
    )
