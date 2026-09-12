# SPDX-License-Identifier: Apache-2.0

import re

import wtforms

from warehouse.i18n import localize as _
from warehouse.oidc.forms._core import PendingPublisherMixin

_VALID_BUILDKITE_SLUG = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,99}$")


def _strip(value: str | None) -> str | None:
    return value.strip() if value else value


class BuildkitePublisherBase(wtforms.Form):
    __params__ = [
        "organization_slug",
        "pipeline_slug",
        "build_branch",
        "build_tag",
        "step_key",
    ]

    organization_slug = wtforms.StringField(
        filters=[_strip],
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify Buildkite organization slug")
            ),
            wtforms.validators.Regexp(
                _VALID_BUILDKITE_SLUG,
                message=_("Invalid Buildkite organization slug"),
            ),
        ],
    )
    pipeline_slug = wtforms.StringField(
        filters=[_strip],
        validators=[
            wtforms.validators.InputRequired(message=_("Specify pipeline slug")),
            wtforms.validators.Regexp(
                _VALID_BUILDKITE_SLUG, message=_("Invalid pipeline slug")
            ),
        ],
    )
    build_branch = wtforms.StringField(
        filters=[_strip], validators=[wtforms.validators.Optional()]
    )
    build_tag = wtforms.StringField(
        filters=[_strip], validators=[wtforms.validators.Optional()]
    )
    step_key = wtforms.StringField(
        filters=[_strip], validators=[wtforms.validators.Optional()]
    )

    @property
    def normalized_organization_slug(self) -> str:
        return (self.organization_slug.data or "").lower()

    @property
    def normalized_pipeline_slug(self) -> str:
        return (self.pipeline_slug.data or "").lower()

    @property
    def normalized_build_branch(self) -> str:
        return self.build_branch.data or ""

    @property
    def normalized_build_tag(self) -> str:
        return self.build_tag.data or ""

    @property
    def normalized_step_key(self) -> str:
        return self.step_key.data or ""


class PendingBuildkitePublisherForm(BuildkitePublisherBase, PendingPublisherMixin):
    __params__ = [*BuildkitePublisherBase.__params__, "project_name"]

    def __init__(self, *args, route_url, check_project_name, user, **kwargs):
        super().__init__(*args, **kwargs)
        self._route_url = route_url
        self._check_project_name = check_project_name
        self._user = user

    @property
    def provider(self) -> str:
        return "buildkite"


class BuildkitePublisherForm(BuildkitePublisherBase):
    pass
