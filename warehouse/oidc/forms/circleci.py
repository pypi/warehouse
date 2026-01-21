# SPDX-License-Identifier: Apache-2.0

import wtforms

from warehouse.i18n import localize as _
from warehouse.oidc.forms._core import PendingPublisherMixin


class CircleCIPublisherBase(wtforms.Form):
    __params__ = [
        "circleci_org_id",
        "circleci_project_id",
        "pipeline_definition_id",
        "context_id",
    ]

    circleci_org_id = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify CircleCI organization ID"),
            ),
            wtforms.validators.UUID(
                message=_("CircleCI organization ID must be a valid UUID"),
            ),
        ]
    )

    circleci_project_id = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify CircleCI project ID"),
            ),
            wtforms.validators.UUID(
                message=_("CircleCI project ID must be a valid UUID"),
            ),
        ]
    )

    pipeline_definition_id = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify CircleCI pipeline definition ID"),
            ),
            wtforms.validators.UUID(
                message=_("CircleCI pipeline definition ID must be a valid UUID"),
            ),
        ]
    )

    context_id = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
            wtforms.validators.UUID(
                message=_("CircleCI context ID must be a valid UUID"),
            ),
        ]
    )


class PendingCircleCIPublisherForm(CircleCIPublisherBase, PendingPublisherMixin):
    __params__ = CircleCIPublisherBase.__params__ + ["project_name"]

    def __init__(self, *args, route_url, check_project_name, user, **kwargs):
        super().__init__(*args, **kwargs)
        self._route_url = route_url
        self._check_project_name = check_project_name
        self._user = user

    @property
    def provider(self) -> str:
        return "circleci"


class CircleCIPublisherForm(CircleCIPublisherBase):
    pass
