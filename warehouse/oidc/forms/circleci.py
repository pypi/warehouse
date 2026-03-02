# SPDX-License-Identifier: Apache-2.0

import requests
import sentry_sdk
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.circleci_org_name: str | None = None
        self.circleci_project_name: str | None = None

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

    def _lookup_project_metadata(self, project_id: str) -> None:
        """Best-effort lookup of project metadata from CircleCI API."""
        # NOTE: The org and project name are meant as a convenience for
        # the user - they are not necessary, but having them display is
        # is a nicer UX for people. The only caveat here is it will NOT
        # work for private projects, but I think thats a fair tradeoff
        try:
            response = requests.get(
                f"https://circleci.com/api/v2/project/{project_id}",
                allow_redirects=True,
                timeout=5,
            )
            if response.status_code == 404:
                # Private project — silently skip.
                return
            response.raise_for_status()
        except requests.HTTPError as exc:
            status_code = getattr(response, "status_code", "unknown")
            response_content = getattr(response, "content", b"")
            sentry_sdk.capture_message(
                "Unexpected error from CircleCI project lookup: "
                f"status={status_code} "
                f"response_content={response_content!r}"
                f" error={exc!r}"
            )
            raise wtforms.validators.ValidationError(
                _(
                    "There is an issue looking up the project with the CircleCI API. "
                    "Try again later."
                )
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            sentry_sdk.capture_message(
                "Connection/timeout error from CircleCI project lookup API"
                f" error={exc!r}"
            )
            raise wtforms.validators.ValidationError(
                _("There is an issue with the CircleCI API. " "Try again later.")
            )

        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            sentry_sdk.capture_message(
                f"Unexpected JSON payload from CircleCI project lookup: "
                f"{response.content!r}"
            )
            raise wtforms.validators.ValidationError(
                _("There is an issue with the CircleCI API. " "Try again later.")
            )
        self.circleci_org_name = data.get("organization_name")
        self.circleci_project_name = data.get("name")

    def validate_circleci_project_id(self, field: wtforms.Field) -> None:
        self._lookup_project_metadata(field.data)

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
