from django import forms
from django.utils.translation import ugettext_lazy as _

from django.contrib.auth.forms import ReadOnlyPasswordHashField

from warehouse import accounts
from warehouse.accounts.models import User


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
        if f is not None:
            f.queryset = f.queryset.select_related("content_type")

    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        # This is done here, rather than on the field, because the
        # field does not have access to the initial value
        return self.initial["password"]
