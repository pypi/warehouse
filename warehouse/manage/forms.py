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


class CreateRoleForm(forms.Form):
    username = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(message="Must specify a username"),
        ]
    )

    role_name = wtforms.SelectField(
        'Select a role',
        choices=[
            ('Owner', 'Owner'),
            ('Maintainer', 'Maintainer'),
        ],
        validators=[
            wtforms.validators.DataRequired(message="Must select a role"),
        ]
    )

    def validate_username(self, field):
        userid = self.user_service.find_userid(field.data)

        if userid is None:
            raise wtforms.validators.ValidationError(
                "No user found with that username. Please try again."
            )

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
