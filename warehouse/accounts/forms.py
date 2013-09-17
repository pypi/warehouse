# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from django import forms
from django.utils.translation import ugettext_lazy as _

from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm

from warehouse import accounts
from warehouse.accounts.models import User


class LoginForm(forms.Form):

    username = forms.CharField(label=_("Username"))
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput)


class SignupForm(forms.Form):

    model = User

    username = forms.RegexField(
                    label=_("Username"),
                    max_length=50,
                    regex=accounts.VALID_USERNAME_REGEX,
                    help_text=accounts.VALID_USERNAME_DESC,
                    error_messages={"invalid": accounts.INVALID_USERNAME_MSG},
                )

    email = forms.EmailField(label=_("Email"), max_length=254)

    password = forms.CharField(
                    label=_("Password"),
                    widget=forms.PasswordInput,
                    min_length=8,
                )

    confirm_password = forms.CharField(
                    label=_("Confirm Password"),
                    widget=forms.PasswordInput,
                )

    def clean_username(self):
        # Ensure that this username is not already taken
        if self.model.api.username_exists(self.cleaned_data["username"]):
            raise forms.ValidationError(_("Username is already taken"))
        return self.cleaned_data["username"]

    def clean_confirm_password(self):
        # Ensure that the confirm_password field matches the password field
        password = self.cleaned_data.get("password", "")
        confirm = self.cleaned_data.get("confirm_password", "")

        if password != confirm:
            raise forms.ValidationError(_("Passwords do not match"))
        return confirm


class UserChangeForm(BaseUserChangeForm):

    username = forms.RegexField(
                    label=_("Username"),
                    max_length=50,
                    regex=accounts.VALID_USERNAME_REGEX,
                    help_text=accounts.VALID_USERNAME_DESC,
                    error_messages={"invalid": accounts.INVALID_USERNAME_MSG},
                )

    class Meta:
        model = User
        fields = "__all__"
