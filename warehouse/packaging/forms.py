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

import wtforms

from warehouse.forms import Form
from warehouse.observations.kinds import ObservationKind


class ReportProjectIssueForm(Form):
    issue_kind = wtforms.fields.SelectField(
        "What is the issue?",
        [wtforms.validators.InputRequired()],
        choices=[(kind._value_, kind.description) for kind in ObservationKind.Project],
    )
    issue_description = wtforms.fields.TextAreaField(
        "Describe the issue, providing as much detail as you are able.",
        [wtforms.validators.InputRequired(), wtforms.validators.Length(max=200)],
    )

    def __init__(self, *args, subject, **kwargs):
        super().__init__(*args, **kwargs)
        self.subject = subject
