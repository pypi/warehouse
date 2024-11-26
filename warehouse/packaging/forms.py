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

from warehouse.forms import PreventHTMLTagsValidator
from warehouse.i18n import localize as _


class SubmitMalwareObservationForm(wtforms.Form):
    """Form to submit details about a Project with Malware"""

    inspector_link = wtforms.fields.URLField(
        validators=[
            wtforms.validators.Length(max=2000),
            wtforms.validators.Regexp(
                r"https://inspector\.pypi\.io/project/[^/]+/",
                message=_("Provide an Inspector link to specific lines of code."),
            ),
        ],
    )

    summary = wtforms.TextAreaField(
        validators=[
            wtforms.validators.InputRequired(),
            wtforms.validators.Length(min=10, max=2000),
            PreventHTMLTagsValidator(),
        ],
    )

    submit = wtforms.SubmitField()
