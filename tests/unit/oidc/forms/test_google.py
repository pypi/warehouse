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

import warehouse

from warehouse.oidc.forms import google


class TestPendingGooglePublisherForm:
    def test_validate(self, monkeypatch):
        project_factory = {}
        data = MultiDict(
            {"email": "some-owner@some-provider.com", "project_name": "some-project"}
        )
        form = google.PendingGooglePublisherForm(
            MultiDict(data),
            api_token=pretend.stub(),
            project_factory=project_factory,
            current_user=pretend.stub(username="some-owner"),
        )

        assert form._project_factory == project_factory
        assert form.validate()

    def test_validate_project_name_already_in_use(self, monkeypatch):
        user = pretend.stub(username="some-owner")
        project_factory = {
            "some-project": pretend.stub(
                owners=[pretend.stub(username="not-some-owner")]
            )
        }
        form = google.PendingGooglePublisherForm(
            api_token="fake-token", project_factory=project_factory, current_user=user
        )

        field = pretend.stub(data="some-project")

        # Bypass localization.
        monkeypatch.setattr(
            warehouse.oidc.forms._core, "_", pretend.call_recorder(lambda s: s)
        )

        with pytest.raises(
            wtforms.validators.ValidationError,
            match="This project name is already in use",
        ):
            form.validate_project_name(field)

    def test_validate_project_already_exists(self, monkeypatch):
        user = pretend.stub(username="some-owner")
        project_factory = {"some-project": pretend.stub(owners=[user])}
        form = google.PendingGooglePublisherForm(
            api_token="fake-token", project_factory=project_factory, current_user=user
        )

        field = pretend.stub(data="some-project")

        # Bypass localization.
        monkeypatch.setattr(
            warehouse.oidc.forms._core, "_", pretend.call_recorder(lambda s: s)
        )

        with pytest.raises(
            wtforms.validators.ValidationError,
            match="Project already exists, create an ordinary trusted "
            "publisher instead",
        ):
            form.validate_project_name(field)
