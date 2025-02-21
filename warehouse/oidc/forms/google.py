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

from warehouse.oidc.forms._core import PendingPublisherMixin


class GooglePublisherBase(wtforms.Form):
    __params__ = ["email", "sub"]

    email = wtforms.fields.EmailField(
        validators=[
            wtforms.validators.InputRequired(),
            wtforms.validators.Email(),
        ]
    )

    sub = wtforms.StringField(validators=[wtforms.validators.Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class PendingGooglePublisherForm(GooglePublisherBase, PendingPublisherMixin):
    __params__ = GooglePublisherBase.__params__ + ["project_name"]

    def __init__(self, *args, route_url, check_project_name, user, **kwargs):
        super().__init__(*args, **kwargs)
        self._route_url = route_url
        self._check_project_name = check_project_name
        self._user = user

    @property
    def provider(self) -> str:
        return "google"


class GooglePublisherForm(GooglePublisherBase):
    pass
