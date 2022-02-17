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
import wtforms

from warehouse import forms
from warehouse.i18n import localize as _

# This roughly matches the "owner/repo" convention used by GitHub.
_VALID_GITHUB_OWNER_REPO_SLUG = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9-]*/[a-zA-Z0-9-_.]+$"
)


class GitHubProviderForm(forms.Form):
    repository_slug = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(message="Specify repository slug"),
        ]
    )

    workflow_name = wtforms.StringField(
        validators=[wtforms.validators.DataRequired(message="Specify workflow name")]
    )

    def validate_repository_slug(self, field):
        repository_slug = field.data
        if not _VALID_GITHUB_OWNER_REPO_SLUG.fullmatch(repository_slug):
            raise wtforms.validators.ValidationError(
                _(
                    "The specified repository is invalid. Repositories must be "
                    "specified in owner/repo format."
                )
            )

        owner, repository = repository_slug.split("/", 1)

        # To actually validate the owner, we ask GitHub's API about them.
        # We can't do this for the repository, since it might be private.
        response = requests.get(
            f"https://api.github.com/users/{owner}",
            headers={"Accept": "application/vnd.github.v3+json"},
            allow_redirects=True,
        )

        if response.status_code == 404:
            raise wtforms.validators.ValidationError(
                _("Unknown GitHub user or organization.")
            )
        elif not response.ok:
            raise wtforms.validators.ValidationError(
                _("Unexpected error from GitHub. Try again.")
            )

        owner_info = response.json()

        # NOTE: Use the normalized owner name as provided by GitHub.
        self.owner = owner_info["login"]
        self.owner_id = owner_info["id"]
        self.repository = repository

    def validate_workflow_name(self, field):
        workflow_name = field.data

        if not (workflow_name.endswith(".yml") or workflow_name.endswith(".yaml")):
            raise wtforms.validators.ValidationError(
                _("Workflow name must end with .yml or .yaml")
            )
