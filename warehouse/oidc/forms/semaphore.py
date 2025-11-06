# SPDX-License-Identifier: Apache-2.0

import wtforms

from warehouse.oidc.forms._core import PendingPublisherMixin


class SemaphorePublisherBase(wtforms.Form):
    __params__ = ["organization", "project"]

    organization = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify organization name"),
            wtforms.validators.Regexp(
                r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$",
                message="Invalid organization name",
            ),
        ]
    )

    project = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify project name"),
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
