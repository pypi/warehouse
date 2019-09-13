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

from datetime import datetime
from datetime import timedelta
import pytz


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

    __params__ = ["name"]

    name = wtforms.StringField()


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


class DeleteTOTPForm(UsernameMixin, forms.Form):

    __params__ = ["confirm_username"]

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


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
            credential_dict = json.loads(field.data.encode("utf8"))
        except json.JSONDecodeError:
            raise wtforms.validators.ValidationError(
                "Invalid WebAuthn credential: Bad payload"
            )

        try:
            validated_credential = self.user_service.verify_webauthn_credential(
                credential_dict,
                challenge=self.challenge,
                rp_id=self.rp_id,
                origin=self.origin,
            )
        except webauthn.RegistrationRejectedException as e:
            raise wtforms.validators.ValidationError(str(e))

        self.validated_credential = validated_credential

    def validate_label(self, field):
        label = field.data

        if self.user_service.get_webauthn_by_label(self.user_id, label) is not None:
            raise wtforms.validators.ValidationError(f"Label '{label}' already in use")


class CreateMacaroonForm(forms.Form):
    __params__ = ["description", "token_scope", "releases", "expiration",]

    def __init__(self, *args, user_id, macaroon_service, all_projects, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = user_id
        self.macaroon_service = macaroon_service
        self.all_projects = all_projects
        self.validated_scope = None

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

    releases = wtforms.StringField(
        validators=[wtforms.validators.DataRequired(message="Specify the release")]
    )

    expiration = wtforms.DateTimeField(
        validators=[
            wtforms.validators.DataRequired(message="Specify the expiration"),
        ]
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
            raise wtforms.ValidationError(f"Specify the token scope")

        if scope_kind == "user":
            self.validated_scope = scope_kind
            return

        try:
            scope_kind, scope_value = scope_kind.split(":", 1)
        except ValueError:
            raise wtforms.ValidationError(f"Unknown token scope: {scope}")

        if scope_kind != "project":
            raise wtforms.ValidationError(f"Unknown token scope: {scope}")
        for project in self.all_projects:
            if scope_value == project.normalized_name:
                return
        raise wtforms.ValidationError(
            f"Unknown or invalid project name: {scope_value}"
        )

    def validate_releases(self,field):
        release = field.data
        try:
            releases = release.split(".")
            for val in releases:
                int(val)
        except ValueError:
            raise wtforms.validators.ValidationError("Invalid release")

        for project in self.all_projects:
            if project.normalized_name == self.validate_token_scope(self.token_scope):
                for version in project.all_versions:
                    if version[0] == release:
                        raise wtforms.validators.ValidationError("Invalid release")
        
    def validate_expiration(self, field):
        expiration = field.data
        expiration = datetime.strptime(expiration, "%Y-%m-%dT%H:%M")
        d = datetime.now()
        tz = pytz.timezone('GMT') # GMT for POC, ideally would be user's local timezone
        tz_aware = tz.localize(d)
        expiration_aware = tz.localize(expiration)

        if expiration_aware > tz_aware + timedelta(days=365):
            raise wtforms.validators.ValidationError("Expiration cannot be greater than one year")
        if expiration_aware < tz_aware:
            raise wtforms.validators.ValidationError("Expiration must be after the current time")
        
        expiration = datetime.strftime(expiration, "%Y-%m-%dT%H:%M")

    def validate(self):
        res = super().validate()
        if not isinstance(self.validated_scope, str):
            self.validated_scope = {"expiration": self.expiration.data, 
            "projects": [{"project-name": self.token_scope.data, "version": self.releases.data}]}   
        return res
        


class DeleteMacaroonForm(forms.Form):
    __params__ = ["macaroon_id"]

    macaroon_id = wtforms.StringField(
        validators=[wtforms.validators.DataRequired(message="Identifier required")]
    )

    def __init__(self, *args, macaroon_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.macaroon_service = macaroon_service

    def validate_macaroon_id(self, field):
        macaroon_id = field.data
        if self.macaroon_service.find_macaroon(macaroon_id) is None:
            raise wtforms.validators.ValidationError("No such macaroon")
