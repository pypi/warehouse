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


class TestPendingGooglePublisherForm:
    def test_validate(self, monkeypatch):
        project_factory = []
        data = MultiDict(
            {
                "sub": "some-subject",
                "email": "some-email@example.com",
                "project_name": "some-project",
            }
        )
        form = google.PendingGooglePublisherForm(
            MultiDict(data), project_factory=project_factory
        )

        assert form._project_factory == project_factory
        assert form.validate()

    def test_validate_project_name_already_in_use(self):
        project_factory = ["some-project"]
        form = google.PendingGooglePublisherForm(project_factory=project_factory)

        field = pretend.stub(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)


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
