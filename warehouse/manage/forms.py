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

import json

import wtforms

import warehouse.utils.otp as otp
import warehouse.utils.webauthn as webauthn

from warehouse import forms
from warehouse.accounts.forms import (
    NewEmailMixin,
    NewPasswordMixin,
    PasswordMixin,
    TOTPValueMixin,
    WebAuthnCredentialMixin,
)
from warehouse.i18n import localize as _
from warehouse.organizations.models import OrganizationRoleType, OrganizationType

# /manage/account/ forms


class RoleNameMixin:

    role_name = wtforms.SelectField(
        "Select role",
        choices=[("", "Select role"), ("Maintainer", "Maintainer"), ("Owner", "Owner")],
        validators=[wtforms.validators.DataRequired(message="Select role")],
    )


class UsernameMixin:

    username = wtforms.StringField(
        validators=[wtforms.validators.DataRequired(message="Specify username")]
    )

    def validate_username(self, field):
        userid = self.user_service.find_userid(field.data)

        if userid is None:
            raise wtforms.validators.ValidationError(
                "No user found with that username. Try again."
            )


class CreateRoleForm(RoleNameMixin, UsernameMixin, forms.Form):
    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class ChangeRoleForm(RoleNameMixin, forms.Form):
    pass


class SaveAccountForm(forms.Form):

    __params__ = ["name", "public_email"]

    name = wtforms.StringField(
        validators=[
            wtforms.validators.Length(
                max=100,
                message=_(
                    "The name is too long. "
                    "Choose a name with 100 characters or less."
                ),
            )
        ]
    )
    public_email = wtforms.SelectField(choices=[("", "Not displayed")])

    def __init__(self, *args, user_service, user_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.user_id = user_id
        user = user_service.get_user(user_id)
        self.public_email.choices.extend(
            [(e.email, e.email) for e in user.emails if e.verified]
        )

    def validate_public_email(self, field):
        if field.data:
            user = self.user_service.get_user(self.user_id)
            verified_emails = [e.email for e in user.emails if e.verified]
            if field.data not in verified_emails:
                raise wtforms.validators.ValidationError(
                    "%s is not a verified email for %s" % (field.data, user.username)
                )


class AddEmailForm(NewEmailMixin, forms.Form):

    __params__ = ["email"]

    def __init__(self, *args, user_service, user_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.user_id = user_id


class ChangePasswordForm(PasswordMixin, NewPasswordMixin, forms.Form):

    __params__ = ["password", "new_password", "password_confirm"]

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class ConfirmPasswordForm(UsernameMixin, PasswordMixin, forms.Form):

    __params__ = ["confirm_password"]

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class DeleteTOTPForm(ConfirmPasswordForm):
    # TODO: delete?
    pass


class ProvisionTOTPForm(TOTPValueMixin, forms.Form):

    __params__ = ["totp_value"]

    def __init__(self, *args, totp_secret, **kwargs):
        super().__init__(*args, **kwargs)
        self.totp_secret = totp_secret

    def validate_totp_value(self, field):
        totp_value = field.data.encode("utf8")
        if not otp.verify_totp(self.totp_secret, totp_value):
            raise wtforms.validators.ValidationError("Invalid TOTP code. Try again?")


class DeleteWebAuthnForm(forms.Form):
    __params__ = ["confirm_device_name"]

    label = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(message="Specify a device name"),
            wtforms.validators.Length(
                max=64, message=("Label must be 64 characters or less")
            ),
        ]
    )

    def __init__(self, *args, user_service, user_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.user_id = user_id

    def validate_label(self, field):
        label = field.data

        webauthn = self.user_service.get_webauthn_by_label(self.user_id, label)
        if webauthn is None:
            raise wtforms.validators.ValidationError("No WebAuthn key with given label")
        self.webauthn = webauthn


class ProvisionWebAuthnForm(WebAuthnCredentialMixin, forms.Form):
    __params__ = ["label", "credential"]

    label = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(message="Specify a label"),
            wtforms.validators.Length(
                max=64, message=("Label must be 64 characters or less")
            ),
        ]
    )

    def __init__(
        self, *args, user_service, user_id, challenge, rp_id, origin, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.user_id = user_id
        self.challenge = challenge
        self.rp_id = rp_id
        self.origin = origin

    def validate_credential(self, field):
        try:
            json.loads(field.data.encode("utf-8"))
        except json.JSONDecodeError:
            raise wtforms.validators.ValidationError(
                "Invalid WebAuthn credential: Bad payload"
            )

        try:
            validated_credential = self.user_service.verify_webauthn_credential(
                field.data.encode("utf-8"),
                challenge=self.challenge,
                rp_id=self.rp_id,
                origin=self.origin,
            )
        except webauthn.RegistrationRejectedError as e:
            raise wtforms.validators.ValidationError(str(e))

        self.validated_credential = validated_credential

    def validate_label(self, field):
        label = field.data

        if self.user_service.get_webauthn_by_label(self.user_id, label) is not None:
            raise wtforms.validators.ValidationError(f"Label '{label}' already in use")


class CreateMacaroonForm(forms.Form):
    __params__ = ["description", "token_scope"]

    def __init__(self, *args, user_id, macaroon_service, project_names, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = user_id
        self.macaroon_service = macaroon_service
        self.project_names = project_names

    description = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(message="Specify a token name"),
            wtforms.validators.Length(
                max=100, message="Description must be 100 characters or less"
            ),
        ]
    )

    token_scope = wtforms.StringField(
        validators=[wtforms.validators.DataRequired(message="Specify the token scope")]
    )

    def validate_description(self, field):
        description = field.data

        if (
            self.macaroon_service.get_macaroon_by_description(self.user_id, description)
            is not None
        ):
            raise wtforms.validators.ValidationError("API token name already in use")

    def validate_token_scope(self, field):
        scope = field.data

        try:
            _, scope_kind = scope.split(":", 1)
        except ValueError:
            raise wtforms.ValidationError(f"Unknown token scope: {scope}")

        if scope_kind == "unspecified":
            raise wtforms.ValidationError("Specify the token scope")

        if scope_kind == "user":
            self.validated_scope = scope_kind
            return

        try:
            scope_kind, scope_value = scope_kind.split(":", 1)
        except ValueError:
            raise wtforms.ValidationError(f"Unknown token scope: {scope}")

        if scope_kind != "project":
            raise wtforms.ValidationError(f"Unknown token scope: {scope}")
        if scope_value not in self.project_names:
            raise wtforms.ValidationError(
                f"Unknown or invalid project name: {scope_value}"
            )

        self.validated_scope = {"projects": [scope_value]}


class DeleteMacaroonForm(UsernameMixin, PasswordMixin, forms.Form):
    __params__ = ["confirm_password", "macaroon_id"]

    macaroon_id = wtforms.StringField(
        validators=[wtforms.validators.DataRequired(message="Identifier required")]
    )

    def __init__(self, *args, macaroon_service, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.macaroon_service = macaroon_service

    def validate_macaroon_id(self, field):
        macaroon_id = field.data
        if self.macaroon_service.find_macaroon(macaroon_id) is None:
            raise wtforms.validators.ValidationError("No such macaroon")


class Toggle2FARequirementForm(forms.Form):
    __params__ = ["two_factor_requirement_sentinel"]

    two_factor_requirement_sentinel = wtforms.HiddenField()


# /manage/organizations/ forms


class OrganizationRoleNameMixin:

    role_name = wtforms.SelectField(
        "Select role",
        choices=[
            ("", "Select role"),
            ("Member", "Member"),
            ("Manager", "Manager"),
            ("Owner", "Owner"),
            ("Billing Manager", "Billing Manager"),
        ],
        coerce=lambda string: OrganizationRoleType(string) if string else None,
        validators=[wtforms.validators.DataRequired(message="Select role")],
    )


class OrganizationNameMixin:

    name = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(
                message="Specify organization account name"
            ),
            wtforms.validators.Length(
                max=50,
                message=_(
                    "Choose an organization account name with 50 characters or less."
                ),
            ),
            # the regexp below must match the CheckConstraint
            # for the name field in organizations.model.Organization
            wtforms.validators.Regexp(
                r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$",
                message=_(
                    "The organization account name is invalid. "
                    "Organization account names "
                    "must be composed of letters, numbers, "
                    "dots, hyphens and underscores. And must "
                    "also start and finish with a letter or number. "
                    "Choose a different organization account name."
                ),
            ),
        ]
    )

    def validate_name(self, field):
        if self.organization_service.find_organizationid(field.data) is not None:
            raise wtforms.validators.ValidationError(
                _(
                    "This organization account name has already been used. "
                    "Choose a different organization account name."
                )
            )


class CreateOrganizationProjectForm(forms.Form):

    __params__ = ["project"]

    project = wtforms.SelectField(
        "Select project",
        choices=[("", "Select project")],
        coerce=lambda x: x,
        validators=[
            wtforms.validators.DataRequired(message="Select project"),
        ],
    )

    def __init__(self, *args, projects_owned, project_factory, **kwargs):
        super().__init__(*args, **kwargs)
        self.project.choices += [(name, name) for name in sorted(projects_owned)]
        self.project.coerce = lambda name: project_factory[name] if name else None


class CreateOrganizationRoleForm(OrganizationRoleNameMixin, UsernameMixin, forms.Form):
    def __init__(self, *args, orgtype, organization_service, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        if orgtype != OrganizationType.Company:
            # Remove "Billing Manager" choice if organization is not a "Company"
            self.role_name.choices = [
                choice
                for choice in self.role_name.choices
                if "Billing Manager" not in choice
            ]
        self.organization_service = organization_service
        self.user_service = user_service


class ChangeOrganizationRoleForm(OrganizationRoleNameMixin, forms.Form):
    def __init__(self, *args, orgtype, **kwargs):
        super().__init__(*args, **kwargs)
        if orgtype != OrganizationType.Company:
            # Remove "Billing Manager" choice if organization is not a "Company"
            self.role_name.choices = [
                choice
                for choice in self.role_name.choices
                if "Billing Manager" not in choice
            ]


class SaveOrganizationNameForm(OrganizationNameMixin, forms.Form):

    __params__ = ["name"]

    def __init__(self, *args, organization_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization_service = organization_service


class SaveOrganizationForm(forms.Form):

    __params__ = ["display_name", "link_url", "description", "orgtype"]

    display_name = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(message="Specify your organization name"),
            wtforms.validators.Length(
                max=100,
                message=_(
                    "The organization name is too long. "
                    "Choose a organization name with 100 characters or less."
                ),
            ),
        ]
    )
    link_url = wtforms.URLField(
        validators=[
            wtforms.validators.DataRequired(message="Specify your organization URL"),
            wtforms.validators.Length(
                max=400,
                message=_(
                    "The organization URL is too long. "
                    "Choose a organization URL with 400 characters or less."
                ),
            ),
        ]
    )
    description = wtforms.TextAreaField(
        validators=[
            wtforms.validators.DataRequired(
                message="Specify your organization description"
            ),
            wtforms.validators.Length(
                max=400,
                message=_(
                    "The organization description is too long. "
                    "Choose a organization description with 400 characters or less."
                ),
            ),
        ]
    )
    orgtype = wtforms.SelectField(
        # TODO: Map additional choices to "Company" and "Community".
        choices=[("Company", "Company"), ("Community", "Community")],
        coerce=OrganizationType,
        validators=[
            wtforms.validators.DataRequired(message="Select organization type"),
        ],
    )


class CreateOrganizationForm(SaveOrganizationNameForm, SaveOrganizationForm):

    __params__ = SaveOrganizationNameForm.__params__ + SaveOrganizationForm.__params__
