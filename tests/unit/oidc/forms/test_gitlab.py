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

from warehouse.oidc.forms import gitlab


class TestPendingGitLabPublisherForm:
    def test_validate(self, monkeypatch):
        project_factory = []
        data = MultiDict(
            {
                "namespace": "some-owner",
                "project": "some-repo",
                "workflow_filepath": "subfolder/some-workflow.yml",
                "project_name": "some-project",
            }
        )
        form = gitlab.PendingGitLabPublisherForm(
            MultiDict(data), project_factory=project_factory
        )

        assert form._project_factory == project_factory
        # We're testing only the basic validation here.
        assert form.validate()

    def test_validate_project_name_already_in_use(self):
        project_factory = ["some-project"]
        form = gitlab.PendingGitLabPublisherForm(project_factory=project_factory)

        field = pretend.stub(data="some-project")
        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_project_name(field)


class TestGitLabPublisherForm:
    @pytest.mark.parametrize(
        "data",
        [
            {
                "namespace": "some-owner",
                "project": "some-repo",
                "workflow_filepath": "subfolder/some-workflow.yml",
            },
            {
                "namespace": "some-group/some-subgroup",
                "project": "some-repo",
                "workflow_filepath": "subfolder/some-workflow.yml",
            },
        ],
    )
    def test_validate(self, data):
        form = gitlab.GitLabPublisherForm(MultiDict(data))

        # We're testing only the basic validation here.
        assert form.validate(), str(form.errors)

    @pytest.mark.parametrize(
        "data",
        [
            {"namespace": None, "project": "some", "workflow_filepath": "some"},
            {"namespace": "", "project": "some", "workflow_filepath": "some"},
            {
                "namespace": "invalid_characters@",
                "project": "some",
                "workflow_filepath": "some",
            },
            {
                "namespace": "invalid_parethen(sis",
                "project": "some",
                "workflow_filepath": "some",
            },
            {
                "namespace": "/start_with_slash",
                "project": "some",
                "workflow_filepath": "some",
            },
            {
                "namespace": "some",
                "project": "invalid space",
                "workflow_filepath": "some",
            },
            {
                "namespace": "some",
                "project": "invalid+plus",
                "workflow_filepath": "some",
            },
            {"project": None, "namespace": "some", "workflow_filepath": "some"},
            {"project": "", "namespace": "some", "workflow_filepath": "some"},
            {
                "project": "$invalid#characters",
                "namespace": "some",
                "workflow_filepath": "some",
            },
            {"project": "some", "namespace": "some", "workflow_filepath": None},
            {"project": "some", "namespace": "some", "workflow_filepath": ""},
        ],
    )
    def test_validate_basic_invalid_fields(self, monkeypatch, data):
        form = gitlab.GitLabPublisherForm(MultiDict(data))

        # We're testing only the basic validation here.
        assert not form.validate()

    @pytest.mark.parametrize(
        "workflow_filepath",
        [
            "missing_suffix",
            "/begin_slash.yml",
            "end_with_slash.yml/",
            "/begin/and/end/slash.yml/",
        ],
    )
    def test_validate_workflow_filepath(self, workflow_filepath):
        form = gitlab.GitLabPublisherForm()
        field = pretend.stub(data=workflow_filepath)

        with pytest.raises(wtforms.validators.ValidationError):
            form.validate_workflow_filepath(field)

    @pytest.mark.parametrize(
        "data, expected",
        [
            ("", ""),
            ("  ", ""),
            ("\t\r\n", ""),
            (None, ""),
        ],
    )
    def test_normalized_environment(self, data, expected):
        form = gitlab.GitLabPublisherForm(environment=data)
        assert form.normalized_environment == expected
