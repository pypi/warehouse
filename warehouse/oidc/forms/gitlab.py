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

import wtforms

from warehouse import forms
from warehouse.i18n import localize as _
from warehouse.oidc.forms._core import PendingPublisherMixin

# https://docs.gitlab.com/ee/user/reserved_names.html#limitations-on-project-and-group-names
_VALID_GITLAB_PROJECT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9]$")
_VALID_GITLAB_NAMESPACE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-_./+]*[a-zA-Z0-9]$")
_VALID_GITLAB_ENVIRONMENT = re.compile(r"^[a-zA-Z0-9\-_/${} ]+$")

_GITLAB_SPECIAL_CHARACTERS = [".", "-", "_"]

_GITLAB_RESERVED_PROJECT_NAMES = {
    "-",
    "badges",
    "blame",
    "blob",
    "builds",
    "commits",
    "create",
    "create_dir",
    "edit",
    "environments/folders",
    "files",
    "find_file",
    "gitlab-lfs/objects",
    "info/lfs/objects",
    "new",
    "preview",
    "raw",
    "refs",
    "tree",
    "update",
    "wikis",
}

_GITLAB_RESERVED_GROUP_NAMES = {
  "-",
  ".well-known",
  "404.html",
  "422.html",
  "500.html",
  "502.html",
  "503.html",
  "admin",
  "api",
  "apple-touch-icon.png",
  "assets",
  "dashboard",
  "deploy.html",
  "explore",
  "favicon.ico",
  "favicon.png",
  "files",
  "groups",
  "health_check",
  "help",
  "import",
  "jwt",
  "login",
  "oauth",
  "profile",
  "projects",
  "public",
  "robots.txt",
  "s",
  "search",
  "sitemap",
  "sitemap.xml",
  "sitemap.xml.gz",
  "slash-command-logo.png",
  "snippets",
  "unsubscribes",
  "uploads",
  "users",
  "v2",
}

_GITLAB_RESERVED_SUBGROUP_NAMES = {
    "-",
}


class CaseInsensitiveNonOf(wtforms.validators.NoneOf):

    def __init__(self, values, message=None, values_formatter=None):
        values = {val.lower() for val in values}
        super().__init__(values, message, values_formatter)

    def __call__(self, form, field):
        field.data = field.data.lower()
        super().__call__(form, field)

def ends_with_atom_or_git(form, field):
    field: str = field.data.lower()
    if field.endswith(".atom") or field.endswith(".git"):
        raise wtforms.validators.ValidationError(
            _("Name ends with .git or .atom")
        )

class ConsecutiveSpecialCharacters:
    def __init__(self, characters: list[str], message: str):
        self.forbidden_characters = characters
        self.message = message

    def __call__(self, form, field):
        countdown = 2
        for char in field.data:
            match char:
                case char if char in self.forbidden_characters:
                    countdown -= 1

                    if countdown == 0:
                        raise wtforms.validators.ValidationError(self.message)

                case _:
                    countdown = 2
class GitLabPublisherBase(forms.Form):
    __params__ = ["namespace", "project", "workflow_filepath", "environment"]

    namespace = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify GitLab namespace (username or group/subgroup)"),
            ),
            ends_with_atom_or_git,
        ]
    )

    project = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify project name")),
            ends_with_atom_or_git,
            CaseInsensitiveNonOf(values=_GITLAB_RESERVED_PROJECT_NAMES),
            wtforms.validators.Regexp(
                _VALID_GITLAB_PROJECT, message=_("Invalid project name")
            ),
            ConsecutiveSpecialCharacters(characters=_GITLAB_SPECIAL_CHARACTERS, message=_("Invalid project name"))
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

    def validate_namespace(self, field):
        group: str = field.data.lower()
        if count := group.count("/"):
            if count != 1:
                raise wtforms.validators.ValidationError(
                    _("Invalid GitLab username or group/subgroup name.")
                )
            group, subgroup = group.split("/")

            if subgroup in _GITLAB_RESERVED_SUBGROUP_NAMES:
                raise wtforms.validators.ValidationError(
                    _("Invalid GitLab username or group/subgroup name.")
                )

        if group in _GITLAB_RESERVED_GROUP_NAMES:
            raise wtforms.validators.ValidationError(
                _("Invalid GitLab username or group/subgroup name.")
            )

        if not _VALID_GITLAB_NAMESPACE.match(group):
            raise wtforms.validators.ValidationError(
                _("Invalid GitLab username or group/subgroup name.")
            )

        ConsecutiveSpecialCharacters(
            characters=_GITLAB_SPECIAL_CHARACTERS, message=_("Invalid GitLab username or group/subgroup name.")
        )(self, field)


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

    def __init__(self, *args, project_factory, **kwargs):
        super().__init__(*args, **kwargs)
        self._project_factory = project_factory


class GitLabPublisherForm(GitLabPublisherBase):
    pass
