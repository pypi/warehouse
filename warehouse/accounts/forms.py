from django import forms
from django.utils.translation import ugettext_lazy as _

from django.contrib.auth.forms import ReadOnlyPasswordHashField

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


class UserChangeForm(forms.ModelForm):

    username = forms.RegexField(
                    label=_("Username"),
                    max_length=50,
                    regex=accounts.VALID_USERNAME_REGEX,
                    help_text=accounts.VALID_USERNAME_DESC,
                    error_messages={"invalid": accounts.INVALID_USERNAME_MSG},
                )
    password = ReadOnlyPasswordHashField(
                    label=_("Password"),
                    help_text=_("Raw passwords are not stored, so there is no "
                                "way to see this user's password, but you can "
                                "change the password using "
                                "<a href=\"password/\">this form</a>.")),

    class Meta:
        model = User

    def __init__(self, *args, **kwargs):
        super(UserChangeForm, self).__init__(*args, **kwargs)

        f = self.fields.get("user_permissions", None)
        f.queryset = f.queryset.select_related("content_type")

    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        # This is done here, rather than on the field, because the
        # field does not have access to the initial value
        return self.initial["password"]
