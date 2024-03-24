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

import re

import packaging.requirements
import packaging.specifiers
import packaging.utils
import packaging.version
import wtforms
import wtforms.validators

from warehouse import forms
from warehouse.utils.project import PROJECT_NAME_RE

_filetype_extension_mapping = {
    "sdist": {".zip", ".tar.gz"},
    "bdist_wheel": {".whl"},
}


def _validate_pep440_version(form, field):
    # Check that this version is a valid PEP 440 version at all.
    try:
        packaging.version.parse(field.data)
    except packaging.version.InvalidVersion:
        raise wtforms.validators.ValidationError(
            "Start and end with a letter or numeral containing only "
            "ASCII numeric and '.', '_' and '-'."
        )


# NOTE: This form validation runs prior to ensuring that the current identity
#       is authorized to upload for the given project, so it should not validate
#       against anything other than what the user themselves have provided.
#
#       Any additional validations (such as duplicate filenames, etc) should
#       occur elsewhere so that they can happen after we've authorized the request
#       to upload for the given project.
class UploadForm(forms.Form):
    # The name and version fields are duplicated out of the general metadata handling,
    # to be part of the upload form as well so that we can use them prior to extracting
    # the metadata from the uploaded artifact.
    #
    # NOTE: We don't need to fully validate these values here, as we will be validating
    #       them fully when we validate the metadata and we will also be ensuring that
    #       these values match the data in the metadata.
    name = wtforms.StringField(
        description="Name",
        validators=[
            wtforms.validators.InputRequired(),
            wtforms.validators.Regexp(
                PROJECT_NAME_RE,
                re.IGNORECASE,
                message=(
                    "Start and end with a letter or numeral containing "
                    "only ASCII numeric and '.', '_' and '-'."
                ),
            ),
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

    # File metadata
    pyversion = wtforms.StringField(validators=[wtforms.validators.Optional()])
    filetype = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(),
            wtforms.validators.AnyOf(
                _filetype_extension_mapping.keys(), message="Use a known file type."
            ),
        ]
    )
    comment = wtforms.StringField(validators=[wtforms.validators.Optional()])
    md5_digest = wtforms.StringField(validators=[wtforms.validators.Optional()])
    sha256_digest = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
            wtforms.validators.Regexp(
                r"^[A-F0-9]{64}$",
                re.IGNORECASE,
                message="Use a valid, hex-encoded, SHA256 message digest.",
            ),
        ]
    )
    blake2_256_digest = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
            wtforms.validators.Regexp(
                r"^[A-F0-9]{64}$",
                re.IGNORECASE,
                message="Use a valid, hex-encoded, BLAKE2 message digest.",
            ),
        ]
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
