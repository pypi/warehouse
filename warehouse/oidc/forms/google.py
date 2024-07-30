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

import re

import wtforms

from warehouse import forms
from warehouse.oidc.forms._core import PendingPublisherMixin

_VALID_GITHUB_REPO = re.compile(r"^[a-zA-Z0-9-_.]+$")
_VALID_GITHUB_OWNER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$")


class GooglePublisherBase(forms.Form):
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

    def __init__(self, *args, project_factory, **kwargs):
        super().__init__(*args, **kwargs)
        self._project_factory = project_factory


class GooglePublisherForm(GooglePublisherBase):
    pass
