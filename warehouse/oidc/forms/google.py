# SPDX-License-Identifier: Apache-2.0

import wtforms

from warehouse.oidc.forms._core import PendingPublisherMixin


class GooglePublisherBase(wtforms.Form):
    __params__ = ["email", "sub"]

    email = wtforms.fields.EmailField(
        validators=[
            wtforms.validators.InputRequired(),
            wtforms.validators.Email(),
        ]
    )

    sub = wtforms.StringField(validators=[wtforms.validators.Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class PendingGooglePublisherForm(GooglePublisherBase, PendingPublisherMixin):
    __params__ = GooglePublisherBase.__params__ + ["project_name"]

    def __init__(self, *args, route_url, check_project_name, user, **kwargs):
        super().__init__(*args, **kwargs)
        self._route_url = route_url
        self._check_project_name = check_project_name
        self._user = user

    @property
    def provider(self) -> str:
        return "google"


class GooglePublisherForm(GooglePublisherBase):
    pass
