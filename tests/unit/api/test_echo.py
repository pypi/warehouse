# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
