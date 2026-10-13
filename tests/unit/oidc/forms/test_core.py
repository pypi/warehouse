# SPDX-License-Identifier: Apache-2.0

import pytest

from webob.multidict import MultiDict

from warehouse.oidc.forms import activestate, github, gitlab, google

from ....common.db.accounts import UserFactory
from ....common.db.packaging import (
    ProhibitedProjectFactory,
    ProjectFactory,
    RoleFactory,
)


@pytest.fixture(
    params=[
        (
            github.PendingGitHubPublisherForm,
            {
                "owner": "some-owner",
                "repository": "some-repo",
                "workflow_filename": "some-workflow.yml",
            },
            {"api_token": "fake-token"},
        ),
        (
            gitlab.PendingGitLabPublisherForm,
            {
                "namespace": "some-owner",
                "project": "some-repo",
                "workflow_filepath": "some-workflow.yml",
                "issuer_url": "https://gitlab.com",
            },
            {"issuer_url_choices": ["https://gitlab.com"]},
        ),
        (
            google.PendingGooglePublisherForm,
            {"sub": "some-subject", "email": "some-email@example.com"},
            {},
        ),
        (
            activestate.PendingActiveStatePublisherForm,
            {
                "organization": "some-org",
                "project": "some-project",
                "actor": "someuser",
            },
            {},
        ),
    ],
    ids=["github", "gitlab", "google", "activestate"],
)
def pending_form(request, project_service, mocker):
    form_class, data, kwargs = request.param
    user = UserFactory.create()
    route_url = mocker.Mock(return_value="/existing-project/publishing")
    # External account lookups are unrelated to PyPI project name validation.
    mocker.patch.object(
        github.PendingGitHubPublisherForm,
        "_lookup_owner",
        return_value={"login": "some-owner", "id": 1234},
    )
    mocker.patch.object(
        activestate.PendingActiveStatePublisherForm,
        "_lookup_actor",
        return_value={"user_id": "some-user-id"},
    )
    mocker.patch.object(
        activestate.PendingActiveStatePublisherForm,
        "_lookup_organization",
        return_value=None,
    )

    def make_form(project_name):
        return form_class(
            MultiDict({**data, "project_name": project_name}),
            check_project_name=project_service.check_project_name,
            route_url=route_url,
            user=user,
            **kwargs,
        )

    return make_form


@pytest.mark.parametrize(
    ("submitted", "expected"),
    [
        (" some-project", "some-project"),
        ("some-project ", "some-project"),
        ("\tsome-project\n", "some-project"),
        ("\u00a0Some_Pkg.Name-1\u00a0", "Some_Pkg.Name-1"),
    ],
)
def test_pending_project_name_strips_surrounding_whitespace(
    pending_form, submitted, expected
):
    form = pending_form(submitted)

    assert form.validate(), form.errors
    assert form.project_name.data == expected
    assert form.data["project_name"] == expected


@pytest.mark.parametrize("submitted", [None, "", " \t\n"])
def test_pending_project_name_blank_is_rejected(pending_form, submitted):
    form = pending_form(submitted)

    assert not form.validate()
    assert form.project_name.errors


def test_pending_project_name_preserves_invalid_internal_whitespace(pending_form):
    form = pending_form("some project")

    assert not form.validate()
    assert "Invalid project name" in form.project_name.errors
    assert form.project_name.data == "some project"


@pytest.mark.parametrize(
    ("submitted", "expected_error"),
    [
        (
            " sys ",
            "This project name isn't allowed (conflict with the Python"
            " standard library module name)",
        ),
        (" forbidden-project ", "This project name isn't allowed"),
        (" foo ", "This project name is too similar to an existing project"),
    ],
)
def test_pending_project_name_still_checks_availability(
    pending_form, submitted, expected_error
):
    ProhibitedProjectFactory.create(name="forbidden-project")
    ProjectFactory.create(name="f00")
    form = pending_form(submitted)

    assert not form.validate()
    assert form.project_name.errors == [expected_error]


@pytest.mark.parametrize("is_owner", [False, True])
def test_pending_project_name_still_rejects_existing_project(
    pending_form, is_owner, pyramid_config
):
    project = ProjectFactory.create(name="Some.Project")
    form = pending_form(" Some.Project ")
    if is_owner:
        RoleFactory.create(user=form._user, project=project)

    assert not form.validate()
    assert len(form.project_name.errors) == 1
    assert "This project already exists" in str(form.project_name.errors[0])
    if is_owner:
        form._route_url.assert_called_once()
        assert form._route_url.call_args.kwargs["project_name"] == "Some.Project"
        assert "/existing-project/publishing" in form.project_name.errors[0]
    else:
        form._route_url.assert_not_called()
