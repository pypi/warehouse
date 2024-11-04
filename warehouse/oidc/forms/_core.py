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
import markupsafe
import wtforms

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
            url_params = {name: value for name, value in self.data.items() if value}
            url_params["provider"] = {self.provider}
            url = self._route_url(
                "manage.project.settings.publishing",
                project_name=project_name,
                _query=url_params,
            )

            # We mark the error message as safe, so that the HTML hyperlink is
            # not escaped by Jinja
            raise wtforms.validators.ValidationError(
                markupsafe.Markup(
                    _(
                        "This project already exists, use the project's publishing"
                        " settings <a href='${url}'>here</a> to create a Trusted"
                        " Publisher for it.",
                        mapping={"url": url},
                    )
                )
            )

    @property
    def provider(self) -> str:  # pragma: no cover
        # Only concrete subclasses are constructed.
        raise NotImplementedError


class DeletePublisherForm(wtforms.Form):
    __params__ = ["publisher_id"]

    publisher_id = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify a publisher ID")),
            wtforms.validators.UUID(message=_("Publisher must be specified by ID")),
        ]
    )
