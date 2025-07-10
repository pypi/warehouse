# SPDX-License-Identifier: Apache-2.0

import re

import wtforms
import wtforms.validators

from warehouse.utils.project import PROJECT_NAME_RE

_filetype_extension_mapping = {
    "sdist": {".zip", ".tar.gz"},
    "bdist_wheel": {".whl"},
}


# NOTE: This form validation runs prior to ensuring that the current identity
#       is authorized to upload for the given project, so it should not validate
#       against anything other than what the user themselves have provided.
#
#       Any additional validations (such as duplicate filenames, etc) should
#       occur elsewhere so that they can happen after we've authorized the request
#       to upload for the given project.
class UploadForm(wtforms.Form):
    # The name field is duplicated out of the general metadata handling, to be
    # part of the upload form as well so that we can use it prior to extracting
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

    def validate(self, _extra_validators=None) -> bool:
        """
        Perform validation on combinations of fields.
        """

        # Validate all defined fields first.
        success = super().validate()
        if not success:
            return False

        # All non source releases *must* have a pyversion
        if (
            self.filetype.data
            and self.filetype.data != "sdist"
            and not self.pyversion.data
        ):
            assert isinstance(self.pyversion.errors, list)
            self.pyversion.errors.append(
                "Python version is required for binary distribution uploads."
            )
            return False

        # All source releases *must* have a pyversion of "source"
        if self.filetype.data == "sdist":
            if not self.pyversion.data:
                self.pyversion.data = "source"
            elif self.pyversion.data != "source":
                assert isinstance(self.pyversion.errors, list)
                self.pyversion.errors.append(
                    "Use 'source' as Python version for an sdist."
                )
                return False

        # We *must* have at least one digest to verify against.
        if (
            not self.md5_digest.data
            and not self.sha256_digest.data
            and not self.blake2_256_digest.data
        ):
            self.form_errors.append("Include at least one message digest.")
            return False

        return success
