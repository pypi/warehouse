# Copyright 2014 Donald Stufft
#
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
from warehouse import forms

_username = forms.StringField(
    forms.validators.Required(),
    forms.validators.Length(min=4, max=25)
)


class LoginForm(forms.Form):

    username = forms.StringField([
        forms.validators.Required(),
        forms.validators.Length(min=4, max=25)
    ])

    password = forms.PasswordField()

    def __init__(self, *args, authenticator, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)

        self.authenticate = authenticator

    def validate_username(self, field):
        if not self.authenticate(field.data, self.password.data):
            raise forms.ValidationError(
                self.gettext("Invalid username or password")
            )


class RegisterForm(forms.Form):

    username = forms.StringField([
        forms.validators.Required(),
        forms.validators.Length(min=4, max=25)
    ])

    email = forms.StringField(
    )

    password = forms.PasswordField()

    confirm_password = forms.PasswordField()

    def __init__(self, *args,
                 is_existing_username,
                 is_existing_email,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self._is_existing_username = is_existing_username
        self._is_existing_email = is_existing_email

    def validate_username(self, field):
        if self._is_existing_username(field.data):
            raise forms.ValidationError(
                self.gettext("Username already exists!")
            )

    def validate_email(self, field):
        if self._is_existing_email(field.data):
            raise forms.ValidationError(
                self.gettext("Email already exists!")
            )

    def validate_confirm_password(self, field):
        if not self.password.data == field.data:
            raise forms.ValidationError(
                self.gettext("Passwords do not match!")
            )
