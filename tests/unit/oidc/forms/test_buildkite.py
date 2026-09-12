# SPDX-License-Identifier: Apache-2.0

import pytest

from webob.multidict import MultiDict

from warehouse.oidc.forms import buildkite


class TestBuildkitePublisherForm:
    def test_validate_and_normalize(self):
        form = buildkite.BuildkitePublisherForm(
            MultiDict(
                {
                    "organization_slug": "  Acme  ",
                    "pipeline_slug": "  Widgets  ",
                    "build_branch": "  main  ",
                    "build_tag": "  ",
                    "step_key": "  publish  ",
                }
            )
        )

        assert form.validate(), form.errors
        assert form.normalized_organization_slug == "acme"
        assert form.normalized_pipeline_slug == "widgets"
        assert form.normalized_build_branch == "main"
        assert form.normalized_build_tag == ""
        assert form.normalized_step_key == "publish"

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("organization_slug", ""),
            ("organization_slug", "-invalid"),
            ("organization_slug", "invalid_slug"),
            ("pipeline_slug", ""),
            ("pipeline_slug", "invalid/slash"),
        ],
    )
    def test_invalid_required_fields(self, field, value):
        data = {
            "organization_slug": "acme",
            "pipeline_slug": "widgets",
        }
        data[field] = value

        form = buildkite.BuildkitePublisherForm(MultiDict(data))

        assert not form.validate()
        assert field in form.errors


class TestPendingBuildkitePublisherForm:
    def test_validate(self, project_service):
        form = buildkite.PendingBuildkitePublisherForm(
            MultiDict(
                {
                    "project_name": "new-project",
                    "organization_slug": "acme",
                    "pipeline_slug": "widgets",
                }
            ),
            route_url=lambda *args, **kwargs: "unused",
            check_project_name=project_service.check_project_name,
            user=None,
        )

        assert form.provider == "buildkite"
        assert form.validate(), form.errors
