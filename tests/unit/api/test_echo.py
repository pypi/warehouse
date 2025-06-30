# SPDX-License-Identifier: Apache-2.0

import pytest

from pyramid.httpexceptions import HTTPAccepted, HTTPBadRequest

from tests.common.db.packaging import ProjectFactory
from warehouse.api.echo import api_echo, api_projects_observations


class TestAPI:
    def test_echo(self, pyramid_request, pyramid_user):
        assert api_echo(pyramid_request) == {"username": pyramid_user.username}


class TestAPIProjectObservations:
    def test_malware_missing_inspector_url(self, pyramid_request):
        project = ProjectFactory.create()
        pyramid_request.json_body = {"kind": "is_malware", "summary": "test"}

        with pytest.raises(HTTPBadRequest) as exc:
            api_projects_observations(project, pyramid_request)

        assert exc.value.json == {
            "error": "missing required fields",
            "missing": ["inspector_url"],
            "project": project.name,
        }

    def test_valid_malware_observation(self, db_request, pyramid_user):
        project = ProjectFactory.create()
        db_request.json_body = {
            "kind": "is_malware",
            "summary": "test",
            "inspector_url": f"https://inspector.pypi.io/project/{project.name}/...",
        }

        response = api_projects_observations(project, db_request)

        assert db_request.response.status == HTTPAccepted().status
        assert response == {
            "project": project.name,
            "thanks": "for the observation",
        }

    def test_valid_spam_observation(self, db_request, pyramid_user):
        project = ProjectFactory.create()
        db_request.json_body = {
            "kind": "is_spam",
            "summary": "test",
        }

        response = api_projects_observations(project, db_request)

        assert db_request.response.status == HTTPAccepted().status
        assert response == {
            "project": project.name,
            "thanks": "for the observation",
        }
