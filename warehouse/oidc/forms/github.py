# SPDX-License-Identifier: Apache-2.0

import re

import requests
import sentry_sdk
import wtforms

from warehouse.i18n import localize as _
from warehouse.oidc.forms._core import PendingPublisherMixin

_VALID_GITHUB_REPO = re.compile(r"^[a-zA-Z0-9-_.]+$")
_VALID_GITHUB_OWNER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$")
_INVALID_ENVIRONMENT_CHARS = re.compile(r'[\x00-\x1F\x7F\'"`,;\\]', re.UNICODE)


class GitHubPublisherBase(wtforms.Form):
    __params__ = ["owner", "repository", "workflow_filename", "environment"]

    owner = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify GitHub repository owner (username or organization)"),
            ),
        ]
    )

    repository = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify repository name")),
            wtforms.validators.Regexp(
                _VALID_GITHUB_REPO, message=_("Invalid repository name")
            ),
        ]
    )

    workflow_filename = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify workflow filename"))
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
                timeout=5,
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

    def validate_environment(self, field):
        environment = field.data

        if not environment:
            return

        if len(environment) > 255:
            raise wtforms.validators.ValidationError(
                _("Environment name is too long (maximum is 255 characters)")
            )

        if environment.startswith(" "):
            raise wtforms.validators.ValidationError(
                _("Environment name may not start with whitespace")
            )

        if environment.endswith(" "):
            raise wtforms.validators.ValidationError(
                _("Environment name may not end with whitespace")
            )

        if _INVALID_ENVIRONMENT_CHARS.search(environment):
            raise wtforms.validators.ValidationError(
                _(
                    "Environment name must not contain non-printable characters "
                    'or the characters "\'", """, "`", ",", ";", "\\"'
                )
            )

    @property
    def normalized_environment(self):
        # The only normalization is due to case-insensitivity.
        #
        # NOTE: We explicitly do not compare `self.environment.data` to None,
        # since it might also be falsey via an empty string.
        return self.environment.data.lower() if self.environment.data else ""


class PendingGitHubPublisherForm(GitHubPublisherBase, PendingPublisherMixin):
    __params__ = GitHubPublisherBase.__params__ + ["project_name"]

    def __init__(self, *args, route_url, check_project_name, user, **kwargs):
        super().__init__(*args, **kwargs)
        self._route_url = route_url
        self._check_project_name = check_project_name
        self._user = user

    @property
    def provider(self) -> str:
        return "github"


class GitHubPublisherForm(GitHubPublisherBase):
    pass
