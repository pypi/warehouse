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
        "vcs_ref",
        "vcs_origin",
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

    # Optional VCS claims for additional security constraints
    # vcs_ref: e.g., "refs/heads/main"
    vcs_ref = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
        ]
    )

    # vcs_origin: e.g., "github.com/organization-123/repo-1"
    vcs_origin = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
        ]
    )

    @property
    def normalized_context_id(self) -> str:
        return self.context_id.data if self.context_id.data else ""

    @property
    def normalized_vcs_ref(self) -> str:
        return self.vcs_ref.data if self.vcs_ref.data else ""

    @property
    def normalized_vcs_origin(self) -> str:
        return self.vcs_origin.data if self.vcs_origin.data else ""


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
