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

from warehouse import forms
from warehouse.i18n import localize as _
from warehouse.utils.project import PROJECT_NAME_RE


class PendingPublisherMixin:
    project_name = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify project name")),
            wtforms.validators.Regexp(
                PROJECT_NAME_RE, message=_("Invalid project name")
            ),
        ]
    )

    def validate_project_name(self, field):
        project_name = field.data

        if project_name in self._project_factory:
            raise wtforms.validators.ValidationError(
                _("This project name is already in use")
            )


class DeletePublisherForm(forms.Form):
    __params__ = ["publisher_id"]

    publisher_id = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify a publisher ID")),
            wtforms.validators.UUID(message=_("Publisher must be specified by ID")),
        ]
    )
