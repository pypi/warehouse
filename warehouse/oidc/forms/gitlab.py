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
import typing

import wtforms

from warehouse.i18n import localize as _
from warehouse.oidc.forms._core import PendingPublisherMixin

# https://docs.gitlab.com/ee/user/reserved_names.html#limitations-on-project-and-group-names
_VALID_GITLAB_PROJECT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9]$")
_VALID_GITLAB_NAMESPACE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-_./+]*[a-zA-Z0-9]$")
_VALID_GITLAB_ENVIRONMENT = re.compile(r"^[a-zA-Z0-9\-_/${} ]+$")

_CONSECUTIVE_SPECIAL_CHARACTERS = re.compile(r"(?!.*[._-]{2})")


def ends_with_atom_or_git(form: wtforms.Form, field: wtforms.Field) -> None:
    field_value = typing.cast(str, field.data).lower()
    if field_value.endswith(".atom") or field_value.endswith(".git"):
        raise wtforms.validators.ValidationError(_("Name ends with .git or .atom"))


class GitLabPublisherBase(wtforms.Form):
    __params__ = ["namespace", "project", "workflow_filepath", "environment"]

    namespace = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify GitLab namespace (username or group/subgroup)"),
            ),
            ends_with_atom_or_git,
            wtforms.validators.Regexp(
                _VALID_GITLAB_NAMESPACE,
                message=_("Invalid GitLab username or group/subgroup name."),
            ),
            wtforms.validators.Regexp(
                _CONSECUTIVE_SPECIAL_CHARACTERS,
                message=_("Invalid GitLab username or group/subgroup name."),
            ),
        ]
    )

    project = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify project name")),
            ends_with_atom_or_git,
            wtforms.validators.Regexp(
                _VALID_GITLAB_PROJECT, message=_("Invalid project name")
            ),
            wtforms.validators.Regexp(
                _CONSECUTIVE_SPECIAL_CHARACTERS,
                message=_("Invalid project name"),
            ),
        ]
    )

    workflow_filepath = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify top-level pipeline file path")
            )
        ]
    )

    environment = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
            wtforms.validators.Regexp(
                _VALID_GITLAB_ENVIRONMENT, message=_("Invalid environment name")
            ),
        ]
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def validate_workflow_filepath(self, field):
        workflow_filepath = field.data

        if not (
            workflow_filepath.endswith(".yml") or workflow_filepath.endswith(".yaml")
        ):
            raise wtforms.validators.ValidationError(
                _("Top-level pipeline file path must end with .yml or .yaml")
            )
        if workflow_filepath.startswith("/") or workflow_filepath.endswith("/"):
            raise wtforms.validators.ValidationError(
                _("Top-level pipeline file path cannot start or end with /")
            )

    @property
    def normalized_environment(self):
        # NOTE: We explicitly do not compare `self.environment.data` to None,
        # since it might also be falsey via an empty string (or might be
        # only whitespace, which we also treat as a None case).
        return (
            self.environment.data
            if self.environment.data and not self.environment.data.isspace()
            else ""
        )


class PendingGitLabPublisherForm(GitLabPublisherBase, PendingPublisherMixin):
    __params__ = GitLabPublisherBase.__params__ + ["project_name"]

    def __init__(self, *args, route_url, check_project_name, **kwargs):
        super().__init__(*args, **kwargs)
        self._route_url = route_url
        self._check_project_name = check_project_name

    @property
    def provider(self) -> str:
        return "gitlab"


class GitLabPublisherForm(GitLabPublisherBase):
    pass
