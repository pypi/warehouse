# SPDX-License-Identifier: Apache-2.0

import wtforms

from warehouse.oidc.forms._core import PendingPublisherMixin


class SemaphorePublisherBase(wtforms.Form):
    __params__ = [
        "organization",
        "semaphore_organization_id",
        "project",
        "semaphore_project_id",
        "repo_slug",
    ]

    organization = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify organization name"),
            wtforms.validators.Regexp(
                r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$",
                message="Invalid organization name",
            ),
        ]
    )

    semaphore_organization_id = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify organization ID"),
        ]
    )

    project = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify project name"),
        ]
    )

    semaphore_project_id = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify project ID"),
        ]
    )

    repo_slug = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify repository (owner/repo)"),
            wtforms.validators.Regexp(
                r"^[^/]+/[^/]+$",
                message="Invalid repository format, expected 'owner/repo'",
            ),
        ]
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class PendingSemaphorePublisherForm(SemaphorePublisherBase, PendingPublisherMixin):
    __params__ = SemaphorePublisherBase.__params__ + ["project_name"]

    def __init__(self, *args, route_url, check_project_name, user, **kwargs):
        super().__init__(*args, **kwargs)
        self._route_url = route_url
        self._check_project_name = check_project_name
        self._user = user

    @property
    def provider(self) -> str:
        return "semaphore"


class SemaphorePublisherForm(SemaphorePublisherBase):
    pass
