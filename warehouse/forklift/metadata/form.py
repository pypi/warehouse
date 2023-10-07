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

import email
import re


import packaging.requirements
import packaging.specifiers
import packaging.utils
import packaging.version
import wtforms
import wtforms.validators

from pyramid.httpexceptions import HTTPBadRequest
from trove_classifiers import classifiers, deprecated_classifiers
from webob.multidict import MultiDict

from warehouse import forms
from warehouse.utils import http
from warehouse.utils.project import PROJECT_NAME_RE

_error_message_order = ["metadata_version", "name", "version"]

_legacy_specifier_re = re.compile(r"^(?P<name>\S+)(?: \((?P<specifier>\S+)\))?$")

_valid_description_content_types = {"text/plain", "text/x-rst", "text/markdown"}

_valid_markdown_variants = {"CommonMark", "GFM"}


def _validate_pep440_version(form, field):
    # Check that this version is a valid PEP 440 version at all.
    try:
        parsed = packaging.version.parse(field.data)
    except packaging.version.InvalidVersion:
        raise wtforms.validators.ValidationError(
            "Start and end with a letter or numeral containing only "
            "ASCII numeric and '.', '_' and '-'."
        )

    # Check that this version does not have a PEP 440 local segment attached
    # to it.
    if parsed.local is not None:
        raise wtforms.validators.ValidationError("Can't use PEP 440 local versions.")


def _parse_legacy_requirement(requirement):
    parsed = _legacy_specifier_re.search(requirement)
    if parsed is None:
        raise ValueError("Invalid requirement.")
    return parsed.groupdict()["name"], parsed.groupdict()["specifier"]


def _validate_pep440_specifier(specifier):
    try:
        packaging.specifiers.SpecifierSet(specifier)
    except packaging.specifiers.InvalidSpecifier:
        raise wtforms.validators.ValidationError(
            "Invalid specifier in requirement."
        ) from None


def _validate_pep440_specifier_field(form, field):
    return _validate_pep440_specifier(field.data)


def _validate_legacy_non_dist_req(requirement):
    try:
        req = packaging.requirements.Requirement(requirement.replace("_", ""))
    except packaging.requirements.InvalidRequirement:
        raise wtforms.validators.ValidationError(
            f"Invalid requirement: {requirement!r}"
        ) from None

    if req.url is not None:
        raise wtforms.validators.ValidationError(
            f"Can't direct dependency: {requirement!r}"
        )

    if any(
        not identifier.isalnum() or identifier[0].isdigit()
        for identifier in req.name.split(".")
    ):
        raise wtforms.validators.ValidationError("Use a valid Python identifier.")


def _validate_legacy_non_dist_req_list(form, field):
    for datum in field.data:
        _validate_legacy_non_dist_req(datum)


def _validate_legacy_dist_req(requirement):
    try:
        req = packaging.requirements.Requirement(requirement)
    except packaging.requirements.InvalidRequirement:
        raise wtforms.validators.ValidationError(
            f"Invalid requirement: {requirement!r}."
        ) from None

    if req.url is not None:
        raise wtforms.validators.ValidationError(
            f"Can't have direct dependency: {requirement!r}"
        )


def _validate_legacy_dist_req_list(form, field):
    for datum in field.data:
        _validate_legacy_dist_req(datum)


def _validate_requires_external(requirement):
    name, specifier = _parse_legacy_requirement(requirement)

    # TODO: Is it really reasonable to parse the specifier using PEP 440?
    if specifier is not None:
        _validate_pep440_specifier(specifier)


def _validate_requires_external_list(form, field):
    for datum in field.data:
        _validate_requires_external(datum)


def _validate_project_url(value):
    try:
        label, url = (x.strip() for x in value.split(",", maxsplit=1))
    except ValueError:
        raise wtforms.validators.ValidationError(
            "Use both a label and an URL."
        ) from None

    if not label:
        raise wtforms.validators.ValidationError("Use a label.")

    if len(label) > 32:
        raise wtforms.validators.ValidationError("Use 32 characters or less.")

    if not url:
        raise wtforms.validators.ValidationError("Use an URL.")

    if not http.is_valid_uri(url, require_authority=False):
        raise wtforms.validators.ValidationError("Use valid URL.")


def _validate_project_url_list(form, field):
    for datum in field.data:
        _validate_project_url(datum)


def _validate_rfc822_email_field(form, field):
    email_validator = wtforms.validators.Email(message="Use a valid email address")
    addresses = email.utils.getaddresses([field.data])

    for real_name, address in addresses:
        email_validator(form, type("field", (), {"data": address}))


def _validate_description_content_type(form, field):
    def _raise(message):
        raise wtforms.validators.ValidationError(
            f"Invalid description content type: {message}"
        )

    msg = email.message.EmailMessage()
    msg["content-type"] = field.data
    content_type, parameters = msg.get_content_type(), msg["content-type"].params
    if content_type not in _valid_description_content_types:
        _raise("type/subtype is not valid")

    charset = parameters.get("charset")
    if charset and charset != "UTF-8":
        _raise("Use a valid charset")

    variant = parameters.get("variant")
    if (
        content_type == "text/markdown"
        and variant
        and variant not in _valid_markdown_variants
    ):
        _raise(
            "Use a valid variant, expected one of {}".format(
                ", ".join(_valid_markdown_variants)
            )
        )


def _validate_no_deprecated_classifiers(form, field):
    invalid_classifiers = set(field.data or []) & deprecated_classifiers.keys()
    if invalid_classifiers:
        first_invalid_classifier_name = sorted(invalid_classifiers)[0]
        deprecated_by = deprecated_classifiers[first_invalid_classifier_name]

        if deprecated_by:
            raise wtforms.validators.ValidationError(
                f"Classifier {first_invalid_classifier_name!r} has been "
                "deprecated, use the following classifier(s) instead: "
                f"{deprecated_by}"
            )
        else:
            raise wtforms.validators.ValidationError(
                f"Classifier {first_invalid_classifier_name!r} has been deprecated."
            )


def _validate_classifiers(form, field):
    invalid = sorted(set(field.data or []) - classifiers)

    if invalid:
        if len(invalid) == 1:
            raise wtforms.validators.ValidationError(
                f"Classifier {invalid[0]!r} is not a valid classifier."
            )
        else:
            raise wtforms.validators.ValidationError(
                f"Classifiers {invalid!r} are not valid classifiers."
            )


# This validated is defined as proper validator rather than a private function
# so that it is better setup for re-use between MetadataForm and UploadForm.
class ProjectName:
    message: str
    _regex: re.Pattern

    def __init__(self, message=None):
        if not message:
            message = (
                "Start and end with a letter or numeral containing "
                "only ASCII numeric and '.', '_' and '-'."
            )
        self.message = message
        self._regex = re.compile(PROJECT_NAME_RE, re.IGNORECASE)

    def __call__(self, form, field):
        if m := self._regex.match(field.data or ""):
            return m

        raise wtforms.validators.ValidationError(self.message)


class ListField(wtforms.Field):
    def process_formdata(self, valuelist):
        self.data = [v.strip() for v in valuelist if v.strip()]


# TODO: Eventually this whole validation thing should move to the packaging
#       library and we should just call that. However until PEP 426 is done
#       that library won't have an API for this.
class MetadataForm(forms.Form):
    # Metadata version
    metadata_version = wtforms.StringField(
        description="Metadata-Version",
        validators=[
            wtforms.validators.InputRequired(),
            wtforms.validators.AnyOf(
                # Note: This isn't really Metadata 2.0, however bdist_wheel
                #       claims it is producing a Metadata 2.0 metadata when in
                #       reality it's more like 1.2 with some extensions.
                ["1.0", "1.1", "1.2", "2.0", "2.1"],
                message="Use a known metadata version.",
            ),
        ],
    )

    # Identity Project and Release
    name = wtforms.StringField(
        description="Name",
        validators=[
            wtforms.validators.InputRequired(),
            ProjectName(),
        ],
    )
    version = wtforms.StringField(
        description="Version",
        validators=[
            wtforms.validators.InputRequired(),
            wtforms.validators.Regexp(
                r"^(?!\s).*(?<!\s)$",
                message="Can't have leading or trailing whitespace.",
            ),
            _validate_pep440_version,
        ],
    )

    # Additional Release metadata
    summary = wtforms.StringField(
        description="Summary",
        validators=[
            wtforms.validators.Optional(),
            wtforms.validators.Length(max=512),
            wtforms.validators.Regexp(
                r"^.+$",  # Rely on the fact that . doesn't match a newline.
                message="Use a single line only.",
            ),
        ],
    )
    description = wtforms.StringField(
        description="Description", validators=[wtforms.validators.Optional()]
    )
    author = wtforms.StringField(
        description="Author", validators=[wtforms.validators.Optional()]
    )
    description_content_type = wtforms.StringField(
        description="Description-Content-Type",
        validators=[wtforms.validators.Optional(), _validate_description_content_type],
    )
    author_email = wtforms.StringField(
        description="Author-email",
        validators=[wtforms.validators.Optional(), _validate_rfc822_email_field],
    )
    maintainer = wtforms.StringField(
        description="Maintainer", validators=[wtforms.validators.Optional()]
    )
    maintainer_email = wtforms.StringField(
        description="Maintainer-email",
        validators=[wtforms.validators.Optional(), _validate_rfc822_email_field],
    )
    license = wtforms.StringField(
        description="License", validators=[wtforms.validators.Optional()]
    )
    keywords = wtforms.StringField(
        description="Keywords", validators=[wtforms.validators.Optional()]
    )
    classifiers = ListField(
        description="Classifier",
        validators=[_validate_no_deprecated_classifiers, _validate_classifiers],
    )
    platform = wtforms.StringField(
        description="Platform", validators=[wtforms.validators.Optional()]
    )

    # URLs
    home_page = wtforms.StringField(
        description="Home-Page",
        validators=[wtforms.validators.Optional(), forms.URIValidator()],
    )
    download_url = wtforms.StringField(
        description="Download-URL",
        validators=[wtforms.validators.Optional(), forms.URIValidator()],
    )

    # Dependency Information
    requires_python = wtforms.StringField(
        description="Requires-Python",
        validators=[wtforms.validators.Optional(), _validate_pep440_specifier_field],
    )

    # Legacy dependency information
    requires = ListField(
        validators=[wtforms.validators.Optional(), _validate_legacy_non_dist_req_list]
    )
    provides = ListField(
        validators=[wtforms.validators.Optional(), _validate_legacy_non_dist_req_list]
    )
    obsoletes = ListField(
        validators=[wtforms.validators.Optional(), _validate_legacy_non_dist_req_list]
    )

    # Newer dependency information
    requires_dist = ListField(
        description="Requires-Dist",
        validators=[wtforms.validators.Optional(), _validate_legacy_dist_req_list],
    )
    provides_dist = ListField(
        description="Provides-Dist",
        validators=[wtforms.validators.Optional(), _validate_legacy_dist_req_list],
    )
    obsoletes_dist = ListField(
        description="Obsoletes-Dist",
        validators=[wtforms.validators.Optional(), _validate_legacy_dist_req_list],
    )
    requires_external = ListField(
        description="Requires-External",
        validators=[wtforms.validators.Optional(), _validate_requires_external_list],
    )

    # Newer metadata information
    project_urls = ListField(
        description="Project-URL",
        validators=[wtforms.validators.Optional(), _validate_project_url_list],
    )

    def full_validate(self):
        # All non source releases *must* have a pyversion
        if (
            self.filetype.data
            and self.filetype.data != "sdist"
            and not self.pyversion.data
        ):
            raise wtforms.validators.ValidationError(
                "Python version is required for binary distribution uploads."
            )

        # All source releases *must* have a pyversion of "source"
        if self.filetype.data == "sdist":
            if not self.pyversion.data:
                self.pyversion.data = "source"
            elif self.pyversion.data != "source":
                raise wtforms.validators.ValidationError(
                    "Use 'source' as Python version for an sdist."
                )

        # We *must* have at least one digest to verify against.
        if (
            not self.md5_digest.data
            and not self.sha256_digest.data
            and not self.blake2_256_digest.data
        ):
            raise wtforms.validators.ValidationError(
                "Include at least one message digest."
            )


def validate(data: MultiDict) -> MetadataForm:
    form = MetadataForm(data)

    if not form.validate():
        for field_name in _error_message_order:
            if field_name in form.errors:
                break
        else:
            field_name = sorted(form.errors.keys())[0]

        if field_name in form:
            field = form[field_name]
            if field.description and isinstance(field, wtforms.StringField):
                error_message = (
                    "{value!r} is an invalid value for {field}. ".format(
                        value=(
                            field.data[:30] + "..." + field.data[-30:]
                            if field.data and len(field.data) > 60
                            else field.data or ""
                        ),
                        field=field.description,
                    )
                    + f"Error: {form.errors[field_name][0]} "
                    + "See "
                    "https://packaging.python.org/specifications/core-metadata"
                    + " for more information."
                )
            else:
                error_message = "Invalid value for {field}. Error: {msgs[0]}".format(
                    field=field_name, msgs=form.errors[field_name]
                )
        else:
            error_message = f"Error: {form.errors[field_name][0]}"

        raise _exc_with_message(HTTPBadRequest, error_message)
