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

from wtforms import Form as BaseForm, StringField
from wtforms.validators import DataRequired, StopValidation, ValidationError
from zxcvbn import zxcvbn

from warehouse.i18n import KNOWN_LOCALES
from warehouse.utils.http import is_valid_uri


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
                raise ValidationError("Invalid field name: {!r}".format(fieldname))

        # Actually ask zxcvbn to check the strength of the given field's data.
        results = zxcvbn(field.data, user_inputs=user_inputs)

        # Determine if the score is too low, and if it is produce a nice error
        # message, *hopefully* with suggestions to make the password stronger.
        if results["score"] < self.required_strength:
            msg = (
                results["feedback"]["warning"]
                if results["feedback"]["warning"]
                else "Password is too easily guessed."
            )
            if results["feedback"]["suggestions"]:
                msg += " " + " ".join(results["feedback"]["suggestions"])
            raise ValidationError(msg)


class Form(BaseForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._form_errors = []

    def validate(self, *args, **kwargs):
        success = super().validate(*args, **kwargs)

        # Determine what form level validators we have to run.
        form_validators = getattr(self.meta, "validators", [])
        full_validate = getattr(self, "full_validate", None)
        if full_validate is not None:
            form_validators.append(full_validate.__func__)

        # Attempt run any form level validators now.
        self._form_errors = []
        for validator in form_validators:
            try:
                validator(self)
            except StopValidation as exc:
                success = False
                if exc.args and exc.args[0]:
                    self._form_errors.append(exc.args[0])
                break
            except ValueError as exc:
                success = False
                self._form_errors.append(exc.args[0])

        return success

    @property
    def errors(self):
        if self._errors is None:
            self._errors = super().errors
            if self._form_errors:
                self._errors["__all__"] = self._form_errors
        return self._errors


class DBForm(Form):
    def __init__(self, *args, db, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = db


class SetLocaleForm(Form):
    __params__ = ["locale_id"]

    locale_id = StringField(validators=[DataRequired(message="Missing locale ID")])

    def validate_locale_id(self, field):
        if field.data not in KNOWN_LOCALES:
            raise ValidationError(f"Unknown locale ID: {field.data}")
