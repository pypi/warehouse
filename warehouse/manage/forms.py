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
from warehouse.organizations.models import (
    OrganizationRoleType,
    OrganizationType,
    TeamProjectRoleType,
)
from warehouse.utils.project import PROJECT_NAME_RE

# /manage/account/ forms


class RoleNameMixin:
    role_name = wtforms.SelectField(
        "Select role",
        choices=[("", "Select role"), ("Maintainer", "Maintainer"), ("Owner", "Owner")],
        validators=[wtforms.validators.InputRequired(message="Select role")],
    )


class TeamProjectRoleNameMixin:
    team_project_role_name = wtforms.SelectField(
        "Select permissions",
        choices=[("", "Select role"), ("Maintainer", "Maintainer"), ("Owner", "Owner")],
        coerce=lambda string: TeamProjectRoleType(string) if string else None,
        validators=[wtforms.validators.InputRequired(message="Select role")],
    )


class UsernameMixin:
    username = wtforms.StringField(
        validators=[wtforms.validators.InputRequired(message="Specify username")]
    )

    def validate_username(self, field):
        userid = self.user_service.find_userid(field.data)

        if userid is None:
            raise wtforms.validators.ValidationError(
                "No user found with that username. Try again."
            )


class CreateRoleForm(RoleNameMixin, UsernameMixin, wtforms.Form):
    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class CreateInternalRoleForm(
    RoleNameMixin,
    TeamProjectRoleNameMixin,
    wtforms.Form,
):
    is_team = wtforms.RadioField(
        "Team or member?",
        choices=[("true", "Team"), ("false", "Member")],
        coerce=lambda string: True if string == "true" else False,
        default="true",
        validators=[wtforms.validators.InputRequired()],
    )

    team_name = wtforms.SelectField(
        "Select team",
        choices=[("", "Select team")],
        default="",  # Set default to avoid error when there are no team choices.
        validators=[wtforms.validators.InputRequired()],
    )

    username = wtforms.SelectField(
        "Select user",
        choices=[("", "Select user")],
        default="",  # Set default to avoid error when there are no user choices.
        validators=[wtforms.validators.InputRequired()],
    )

    def __init__(self, *args, team_choices, user_choices, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.team_name.choices += [(name, name) for name in sorted(team_choices)]
        self.username.choices += [(name, name) for name in sorted(user_choices)]
        self.user_service = user_service

        # Do not check for required fields in browser.
        self.team_name.flags.required = False
        self.team_project_role_name.flags.required = False
        self.username.flags.required = False
        self.role_name.flags.required = False

        # Conditionally check for required fields on server.
        if self.is_team.data:
            self.username.validators = []
            self.role_name.validators = []
        else:
            self.team_name.validators = []
            self.team_project_role_name.validators = []


class ChangeRoleForm(RoleNameMixin, wtforms.Form):
    pass


class ChangeTeamProjectRoleForm(TeamProjectRoleNameMixin, wtforms.Form):
    pass


class SaveAccountForm(wtforms.Form):
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
                    f"{field.data} is not a verified email for {user.username}"
                )


class AddEmailForm(NewEmailMixin, wtforms.Form):
    __params__ = ["email"]

    def __init__(self, *args, user_service, user_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.user_id = user_id


class ChangePasswordForm(PasswordMixin, NewPasswordMixin, wtforms.Form):
    __params__ = ["password", "new_password", "password_confirm"]

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class ConfirmPasswordForm(UsernameMixin, PasswordMixin, wtforms.Form):
    __params__ = ["confirm_password"]

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class DeleteTOTPForm(ConfirmPasswordForm):
    # TODO: delete?
    pass


class ProvisionTOTPForm(TOTPValueMixin, wtforms.Form):
    __params__ = ["totp_value"]

    def __init__(self, *args, totp_secret, **kwargs):
        super().__init__(*args, **kwargs)
        self.totp_secret = totp_secret

    def validate_totp_value(self, field):
        totp_value = field.data.encode("utf8")
        try:
            otp.verify_totp(self.totp_secret, totp_value)
        except otp.OutOfSyncTOTPError:
            raise wtforms.validators.ValidationError(
                "Invalid TOTP code. Your device time may be out of sync."
            )
        except otp.InvalidTOTPError:
            raise wtforms.validators.ValidationError("Invalid TOTP code. Try again?")


class DeleteWebAuthnForm(wtforms.Form):
    __params__ = ["confirm_device_name"]

    label = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify a device name"),
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


class ProvisionWebAuthnForm(WebAuthnCredentialMixin, wtforms.Form):
    __params__ = ["label", "credential"]

    label = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify a label"),
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


class CreateMacaroonForm(wtforms.Form):
    __params__ = ["description", "token_scope"]

    def __init__(
        self,
        *args,
        user_id,
        macaroon_service,
        project_names,
        selected_project=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.user_id = user_id
        self.macaroon_service = macaroon_service
        self.project_names = project_names
        if selected_project is not None:
            self.token_scope.data = self.scope_prefix + selected_project

    description = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify a token name"),
            wtforms.validators.Length(
                max=100, message="Description must be 100 characters or less"
            ),
        ]
    )

    token_scope = wtforms.StringField(
        validators=[wtforms.validators.InputRequired(message="Specify the token scope")]
    )

    scope_prefix = "scope:project:"

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


class DeleteMacaroonForm(UsernameMixin, PasswordMixin, wtforms.Form):
    __params__ = ["confirm_password", "macaroon_id"]

    macaroon_id = wtforms.StringField(
        validators=[wtforms.validators.InputRequired(message="Identifier required")]
    )

    def __init__(self, *args, macaroon_service, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.macaroon_service = macaroon_service

    def validate_macaroon_id(self, field):
        macaroon_id = field.data
        if self.macaroon_service.find_macaroon(macaroon_id) is None:
            raise wtforms.validators.ValidationError("No such macaroon")


# /manage/organizations/ forms


class InformationRequestResponseForm(wtforms.Form):
    response = wtforms.TextAreaField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Provide your response to the request.")
            )
        ]
    )


class OrganizationActivateBillingForm(wtforms.Form):
    terms_of_service_agreement = wtforms.BooleanField(
        validators=[
            wtforms.validators.DataRequired(
                message="Terms of Service must be accepted.",
            ),
        ],
        default=False,
    )


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
        validators=[wtforms.validators.InputRequired(message="Select role")],
    )


class OrganizationNameMixin:
    name = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message="Specify organization account name"
            ),
            wtforms.validators.Length(
                max=50,
                message=_(
                    "Choose an organization account name with 50 characters or less."
                ),
            ),
            # the regexp below must match the CheckConstraint
            # for the name field in organizations.models.Organization
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

    organization_id = None

    def validate_name(self, field):
        # Find organization by name.
        organization_id = self.organization_service.find_organizationid(field.data)

        # Name is valid if one of the following is true:
        # - There is no name conflict with any organization.
        # - The name conflict is with the current organization.
        if organization_id is not None and organization_id != self.organization_id:
            raise wtforms.validators.ValidationError(
                _(
                    "This organization account name has already been used. "
                    "Choose a different organization account name."
                )
            )

        outstanding_applications = (
            self.organization_service.get_organization_applications_by_name(
                field.data, submitted_by=self.user, undecided=True
            )
        )

        # Name is valid if the user has no outstanding applications for the same name
        if len(outstanding_applications) > 0:
            raise wtforms.validators.ValidationError(
                _(
                    "You have already submitted an application for that name. "
                    "Choose a different organization account name."
                )
            )


class AddOrganizationProjectForm(wtforms.Form):
    __params__ = ["add_existing_project", "existing_project_name", "new_project_name"]

    add_existing_project = wtforms.RadioField(
        "Add existing or new project?",
        choices=[("true", "Existing project"), ("false", "New project")],
        coerce=lambda string: True if string == "true" else False,
        default="true",
        validators=[wtforms.validators.InputRequired()],
    )

    existing_project_name = wtforms.SelectField(
        "Select project",
        choices=[("", "Select project")],
        default="",  # Set default to avoid error when there are no project choices.
    )

    new_project_name = wtforms.StringField()

    def __init__(self, *args, project_choices, project_factory, **kwargs):
        super().__init__(*args, **kwargs)
        self.existing_project_name.choices += [
            (name, name) for name in sorted(project_choices)
        ]
        self.project_factory = project_factory

    def validate_existing_project_name(self, field):
        if self.add_existing_project.data:
            if not field.data:
                raise wtforms.validators.StopValidation(_("Select project"))

    def validate_new_project_name(self, field):
        if not self.add_existing_project.data:
            if not field.data:
                raise wtforms.validators.StopValidation(_("Specify project name"))
            if not PROJECT_NAME_RE.match(field.data):
                raise wtforms.validators.ValidationError(
                    _(
                        "Start and end with a letter or numeral containing "
                        "only ASCII numeric and '.', '_' and '-'."
                    )
                )
            if field.data in self.project_factory:
                raise wtforms.validators.ValidationError(
                    _(
                        "This project name has already been used. "
                        "Choose a different project name."
                    )
                )


class TransferOrganizationProjectForm(wtforms.Form):
    __params__ = ["organization"]

    organization = wtforms.SelectField(
        "Select organization",
        choices=[("", "Select organization")],
        validators=[
            wtforms.validators.InputRequired(message="Select organization"),
        ],
    )

    def __init__(self, *args, organization_choices, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization.choices += [
            (name, name) for name in sorted(organization_choices)
        ]


class CreateOrganizationRoleForm(
    OrganizationRoleNameMixin, UsernameMixin, wtforms.Form
):
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


class ChangeOrganizationRoleForm(OrganizationRoleNameMixin, wtforms.Form):
    def __init__(self, *args, orgtype, **kwargs):
        super().__init__(*args, **kwargs)
        if orgtype != OrganizationType.Company:
            # Remove "Billing Manager" choice if organization is not a "Company"
            self.role_name.choices = [
                choice
                for choice in self.role_name.choices
                if "Billing Manager" not in choice
            ]


class SaveOrganizationNameForm(OrganizationNameMixin, wtforms.Form):
    __params__ = ["name"]

    def __init__(
        self, *args, organization_service, organization_id=None, user, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.organization_service = organization_service
        self.organization_id = organization_id
        self.user = user


class SaveOrganizationForm(wtforms.Form):
    __params__ = ["display_name", "link_url", "description", "orgtype"]

    display_name = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify your organization name"),
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
            wtforms.validators.InputRequired(message="Specify your organization URL"),
            wtforms.validators.Length(
                max=400,
                message=_(
                    "The organization URL is too long. "
                    "Choose a organization URL with 400 characters or less."
                ),
            ),
            wtforms.validators.Regexp(
                r"^https?://",
                message=_("The organization URL must start with http:// or https://"),
            ),
        ]
    )
    description = wtforms.TextAreaField(
        validators=[
            wtforms.validators.InputRequired(
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
        choices=[("Company", "Company"), ("Community", "Community")],
        coerce=OrganizationType,
        validators=[
            wtforms.validators.InputRequired(message="Select organization type"),
        ],
    )


class CreateOrganizationApplicationForm(OrganizationNameMixin, SaveOrganizationForm):
    __params__ = ["name"] + SaveOrganizationForm.__params__

    _max_apps = wtforms.IntegerField()

    def __init__(
        self, *args, organization_service, user, max_applications=None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.organization_service = organization_service
        self.user = user
        self.max_applications = max_applications

    def validate__max_apps(self, field):
        if (
            self.max_applications is not None
            and len(self.user.organization_applications) >= self.max_applications
        ):
            self.form_errors.append(
                _(
                    "You have already submitted the maximum number of "
                    f"Organization requests ({self.max_applications})."
                )
            )
            return False
        return True


class CreateTeamRoleForm(wtforms.Form):
    username = wtforms.SelectField(
        "Select user",
        choices=[("", "Select user")],
        default="",  # Set default to avoid error when there are no user choices.
        validators=[wtforms.validators.InputRequired()],
    )

    def __init__(self, *args, user_choices, **kwargs):
        super().__init__(*args, **kwargs)
        self.username.choices += [(name, name) for name in sorted(user_choices)]


class SaveTeamForm(wtforms.Form):
    __params__ = ["name"]

    name = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message="Specify team name"),
            wtforms.validators.Length(
                max=50,
                message=_("Choose a team name with 50 characters or less."),
            ),
            # the regexp below must match the CheckConstraint
            # for the name field in organizations.models.Team
            wtforms.validators.Regexp(
                r"^([^\s/._-]|[^\s/._-].*[^\s/._-])$",
                message=_(
                    "The team name is invalid. Team names cannot start "
                    "or end with a space, period, underscore, hyphen, "
                    "or slash. Choose a different team name."
                ),
            ),
        ]
    )

    def __init__(
        self, *args, organization_service, organization_id, team_id=None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.team_id = team_id
        self.organization_id = organization_id
        self.organization_service = organization_service

    def validate_name(self, field):
        # Find team by name.
        team_id = self.organization_service.find_teamid(
            self.organization_id, field.data
        )

        # Name is valid if one of the following is true:
        # - There is no name conflict with any team.
        # - The name conflict is with the current team.
        if team_id is not None and team_id != self.team_id:
            raise wtforms.validators.ValidationError(
                _(
                    "This team name has already been used. "
                    "Choose a different team name."
                )
            )


class CreateTeamForm(SaveTeamForm):
    __params__ = SaveTeamForm.__params__


class AddAlternateRepositoryForm(wtforms.Form):
    """Form to add an Alternate Repository Location for a Project."""

    __params__ = ["display_name", "link_url", "description"]

    display_name = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify your alternate repository name"),
            ),
            wtforms.validators.Length(
                max=100,
                message=_(
                    "The name is too long. "
                    "Choose a name with 100 characters or less."
                ),
            ),
        ]
    )
    link_url = wtforms.URLField(
        validators=[
            wtforms.validators.InputRequired(
                message=_("Specify your alternate repository URL"),
            ),
            wtforms.validators.Length(
                max=400,
                message=_(
                    "The URL is too long. Choose a URL with 400 characters or less."
                ),
            ),
            forms.URIValidator(),
        ]
    )
    description = wtforms.TextAreaField(
        validators=[
            wtforms.validators.InputRequired(
                message="Describe the purpose and content of the alternate repository."
            ),
            wtforms.validators.Length(
                max=400,
                message=_(
                    "The description is too long. "
                    "Choose a description with 400 characters or less."
                ),
            ),
        ]
    )
