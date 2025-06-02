# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING

from nh3 import is_html
from wtforms import Form as BaseForm, StringField
from wtforms.validators import InputRequired, ValidationError
from zxcvbn import zxcvbn

from warehouse.constants import MAX_PASSWORD_SIZE
from warehouse.i18n import KNOWN_LOCALES
from warehouse.utils.http import is_valid_uri

if TYPE_CHECKING:
    from wtforms.fields import Field


class URIValidator:
    def __init__(
        self,
        require_scheme=True,
        allowed_schemes={"http", "https"},
        require_authority=True,
    ):
        self.require_scheme = require_scheme
        self.allowed_schemes = allowed_schemes
        self.require_authority = require_authority

    def __call__(self, form, field):
        if not is_valid_uri(
            field.data,
            require_authority=self.require_authority,
            allowed_schemes=self.allowed_schemes,
            require_scheme=self.require_scheme,
        ):
            raise ValidationError("Invalid URI")


class PasswordStrengthValidator:
    # From the zxcvbn documentation, a score of 2 is:
    #       somewhat guessable: protection from unthrottled online attacks.
    #       (guesses < 10^8)
    # So we're going to require at least a score of 2 to be a valid password.
    # That should (ideally) provide protection against all attacks that don't
    # involve a lost database dump.
    def __init__(self, *, user_input_fields=None, required_strength=2):
        self.user_input_fields = user_input_fields or []
        self.required_strength = required_strength

    def __call__(self, form, field):
        # Get all of our additional data to be used as user input to zxcvbn.
        user_inputs = []
        for fieldname in self.user_input_fields:
            try:
                user_inputs.append(form[fieldname].data)
            except KeyError:
                raise ValidationError(f"Invalid field name: {fieldname!r}")

        # Actually ask zxcvbn to check the strength of the given field's data.
        results = zxcvbn(
            field.data, user_inputs=user_inputs, max_length=MAX_PASSWORD_SIZE
        )

        # Determine if the score is too low, and if it is produce a nice error
        # message, *hopefully* with suggestions to make the password stronger.
        if results["score"] < self.required_strength:
            msg = (
                results["feedback"]["warning"]
                if results["feedback"]["warning"]
                # Note: we can't localize this string because it will be mixed
                # with other non-localizable strings from zxcvbn
                else "Password is too easily guessed."
            )
            if results["feedback"]["suggestions"]:
                msg += " " + " ".join(results["feedback"]["suggestions"])
            raise ValidationError(msg)


class PreventHTMLTagsValidator:
    """
    Validate the field to ensure that it does not contain any HTML tags.
    """

    def __init__(self, message: str | None = None):
        if message is None:
            message = "HTML tags are not allowed"
        self.message = message

    def __call__(self, form: BaseForm, field: Field):
        if is_html(field.data):
            raise ValidationError(self.message)


class SetLocaleForm(BaseForm):
    __params__ = ["locale_id"]

    locale_id = StringField(validators=[InputRequired(message="Missing locale ID")])

    def validate_locale_id(self, field):
        if field.data not in KNOWN_LOCALES.keys():
            raise ValidationError(f"Unknown locale ID: {field.data}")
