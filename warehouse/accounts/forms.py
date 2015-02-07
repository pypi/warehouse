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
from warehouse.accounts.models import User


class LoginForm(forms.DBForm):

    username = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Length(max=50),
        ],
    )

    password = wtforms.PasswordField(
        validators=[
            wtforms.validators.DataRequired(),
        ],
    )

    def __init__(self, *args, password_hasher, **kwargs):
        super().__init__(*args, **kwargs)
        self.password_hasher = password_hasher
        self.user = None

    def validate_username(self, field):
        # Attempt to fetch the user from the database.
        self.user = (
            self.db.query(User).filter(User.username == field.data).first()
        )

        # If the user doesn't exist, then this form is invalid.
        if self.user is None:
            raise wtforms.validators.ValidationError("Invalid User")

        # If the given username is different than the username in the database
        # we'll go ahead and coerce it to the correct value.
        if self.user.username != field.data:
            field.data = self.user.username

    def validate_password(self, field):
        if self.user is not None:
            ok, new_hash = self.password_hasher.verify_and_update(
                field.data,
                self.user.password,
            )

            # Check if the given password was OK.
            if not ok:
                raise wtforms.validators.ValidationError("Invalid password.")

            # Check if we've gotten a new hash from the password hasher.
            if new_hash:
                self.user.password = new_hash
