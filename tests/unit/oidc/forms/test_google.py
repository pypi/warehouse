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

import pretend
import pytest
import wtforms

from webob.multidict import MultiDict

from warehouse.oidc.forms import google
from warehouse.packaging.interfaces import ProjectNameUnavailableExisting


class TestPendingGooglePublisherForm:
    def test_validate(self, monkeypatch):
        route_url = pretend.stub()
        user = pretend.stub()

        def check_project_name(name):
            return None  # Name is available.

        data = MultiDict(
            {
                "sub": "some-subject",
                "email": "some-email@example.com",
                "project_name": "some-project",
            }
        )
        form = google.PendingGooglePublisherForm(
            MultiDict(data),
            route_url=route_url,
            check_project_name=check_project_name,
            user=user,
        )

        assert form._check_project_name == check_project_name
        assert form._route_url == route_url
        assert form._user == user
        assert form.validate()

    def test_validate_project_name_already_in_use_owner(self, pyramid_config):
        user = pretend.stub()
        owners = [user]
        route_url = pretend.call_recorder(lambda *args, **kwargs: "my_url")
        form = google.PendingGooglePublisherForm(
            route_url=route_url,
            check_project_name=lambda name: ProjectNameUnavailableExisting(
                existing_project=pretend.stub(owners=owners)
            ),
            user=user,
        )

        field = pretend.stub(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)

        # The project settings URL is only shown in the error message if
        # the user is the owner of the project
        assert route_url.calls == [
            pretend.call(
                "manage.project.settings.publishing",
                project_name="some-project",
                _query={"provider": {"google"}},
            )
        ]

    def test_validate_project_name_already_in_use_not_owner(self, pyramid_config):
        user = pretend.stub()
        owners = []
        route_url = pretend.call_recorder(lambda *args, **kwargs: "my_url")
        form = google.PendingGooglePublisherForm(
            route_url=route_url,
            check_project_name=lambda name: ProjectNameUnavailableExisting(
                existing_project=pretend.stub(owners=owners)
            ),
            user=user,
        )

        field = pretend.stub(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)

        assert route_url.calls == []


class TestGooglePublisherForm:
    @pytest.mark.parametrize(
        ("sub", "email"),
        [
            (None, "some-email@example.com"),
            ("some-subject", "some-email@example.com"),
        ],
    )
    def test_validate(self, monkeypatch, sub, email):
        data = MultiDict(
            {
                "sub": sub,
                "email": email,
            }
        )
        form = google.GooglePublisherForm(MultiDict(data))

        assert form.validate(), str(form.errors)

    @pytest.mark.parametrize(
        ("sub", "email"),
        [
            ("", ""),
            (None, ""),
            ("some-subject", ""),
            ("some-subject", "invalid_email"),
        ],
    )
    def test_validate_basic_invalid_fields(self, monkeypatch, sub, email):
        data = MultiDict(
            {
                "sub": sub,
                "email": email,
            }
        )

        form = google.GooglePublisherForm(MultiDict(data))
        assert not form.validate()
