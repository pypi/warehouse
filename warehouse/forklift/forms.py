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

import cgi
import re

import packaging.utils
import wtforms
import wtforms.validators


from warehouse import forms
from warehouse.utils.project import PROJECT_NAME_RE

# Wheel platform checking

# Note: defining new platform ABI compatibility tags that don't
#       have a python.org binary release to anchor them is a
#       complex task that needs more than just OS+architecture info.
#       For Linux specifically, the platform ABI is defined by each
#       individual distro version, so wheels built on one version may
#       not even work on older versions of the same distro, let alone
#       a completely different distro.
#
#       That means new entries should only be added given an
#       accompanying ABI spec that explains how to build a
#       compatible binary (see the manylinux specs as examples).

# These platforms can be handled by a simple static list:
_allowed_platforms = {
    "any",
    "win32",
    "win_arm64",
    "win_amd64",
    "win_ia64",
    "manylinux1_x86_64",
    "manylinux1_i686",
    "manylinux2010_x86_64",
    "manylinux2010_i686",
    "manylinux2014_x86_64",
    "manylinux2014_i686",
    "manylinux2014_aarch64",
    "manylinux2014_armv7l",
    "manylinux2014_ppc64",
    "manylinux2014_ppc64le",
    "manylinux2014_s390x",
    "linux_armv6l",
    "linux_armv7l",
}
# macosx is a little more complicated:
_macosx_platform_re = re.compile(r"macosx_(?P<major>\d+)_(\d+)_(?P<arch>.*)")
_macosx_arches = {
    "ppc",
    "ppc64",
    "i386",
    "x86_64",
    "arm64",
    "intel",
    "fat",
    "fat32",
    "fat64",
    "universal",
    "universal2",
}
_macosx_major_versions = {
    "10",
    "11",
    "12",
    "13",
    "14",
}

# manylinux pep600 and musllinux pep656 are a little more complicated:
_linux_platform_re = re.compile(r"(?P<libc>(many|musl))linux_(\d+)_(\d+)_(?P<arch>.*)")
_jointlinux_arches = {
    "x86_64",
    "i686",
    "aarch64",
    "armv7l",
    "ppc64le",
    "s390x",
}
_manylinux_arches = _jointlinux_arches | {"ppc64"}
_musllinux_arches = _jointlinux_arches


# Actual checking code;
def _valid_platform_tag(platform_tag):
    if platform_tag in _allowed_platforms:
        return True
    m = _macosx_platform_re.match(platform_tag)
    if (
        m
        and m.group("major") in _macosx_major_versions
        and m.group("arch") in _macosx_arches
    ):
        return True
    m = _linux_platform_re.match(platform_tag)
    if m and m.group("libc") == "musl":
        return m.group("arch") in _musllinux_arches
    if m and m.group("libc") == "many":
        return m.group("arch") in _manylinux_arches
    return False


_dist_file_re = re.compile(r".+?(?P<extension>\.(tar\.gz|zip|whl))$", re.I)

_filetype_extension_mapping = {
    "sdist": {".zip", ".tar.gz"},
    "bdist_wheel": {".whl"},
}


# We make a custom FileField, because WTForms doesn't really understand the
# cgi.FieldStorage that Pyramid and our upload API ends up using.
class FileField(wtforms.FileField):
    def process_formdata(self, valuelist):
        if valuelist:
            value = valuelist[0]
            if isinstance(value, cgi.FieldStorage):
                # The FileField class doesn't attempt to handle the actual file data,
                # it only validates that a file was uploaded, and gives you the
                # filename that was used.
                self.data = value.filename


def _validate_filename(form, field):
    # Our object storage does not tolerate some specific characters
    # ref: https://www.backblaze.com/b2/docs/files.html#file-names
    #
    # Also, its hard to imagine a usecase for them that isn't ✨malicious✨
    # or completely by mistake.
    disallowed = [*(chr(x) for x in range(32)), chr(127)]
    if [char for char in field.data if char in disallowed]:
        raise wtforms.validators.ValidationError(
            "Cannot upload a file with "
            "non-printable characters (ordinals 0-31) "
            "or the DEL character (ordinal 127) "
            "in the name."
        )

    # Make sure that the filename does not contain any path separators.
    if "/" in field.data or "\\" in field.data:
        raise wtforms.validators.ValidationError(
            "Cannot upload a file with '/' or '\\' in the name."
        )

    # Make sure the filename ends with an allowed extension.
    if not _dist_file_re.match(field.data):
        raise wtforms.validators.ValidationError(
            "Invalid file extension: Use .tar.gz, .whl or .zip "
            "extension. See https://www.python.org/dev/peps/pep-0527 "
            "and https://peps.python.org/pep-0715/ for more information",
        )


def _validate_wheel_platform_tags(form, field):
    # If this isn't a wheel, then we skip this validator
    if not field.data.endswith(".whl"):
        return

    try:
        _, _, _, tags = packaging.utils.parse_wheel_filename(field.data)
    except packaging.utils.InvalidWheelFilename as exc:
        raise wtforms.validators.ValidationError(str(exc))

    for tag in tags:
        if not _valid_platform_tag(tag.platform):
            raise wtforms.validators.ValidationError(
                f"Binary wheel {field.data!r} has an unsupported "
                f"platform tag {tag.platform!r}"
            )


def _validate_filename_for_filetype(filename, filetype):
    if m := _dist_file_re.match(filename):
        extension = m.group("extension")
        if extension not in _filetype_extension_mapping[filetype]:
            raise wtforms.validators.ValidationError(
                f"Invalid file extension: Extension {extension} is invalid for "
                f"filetype {filetype}. See "
                "https://www.python.org/dev/peps/pep-0527 for more information.",
            )


# NOTE: This form validation runs prior to ensuring that the current identity
#       is authorized to upload for the given project, so it should not validate
#       against anything other than what the user themselves have provided.
#
#       Any additional validations (such as duplicate filenames, etc) should
#       occur elsewhere so that they can happen after we've authorized the request
#       to upload for the given project.
class UploadForm(forms.Form):
    # This field is duplicated out of the general metadata handling, to be part
    # of the upload form as well.
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

    # This is the actual uploaded file
    filename = FileField(
        # This name comes from legacy PyPI, and cannot easily be changed without
        # breaking all of the existing upload clients.
        name="content",
        validators=[
            # We purposely use DataRequired here, because we want to have this
            # work on coerced field data, not on the input data.
            wtforms.validators.DataRequired(),
            # Ensure the filename doesn't contain any characters that are
            # too 🌶️spicy🥵
            _validate_filename,
            # Check that if it's a binary wheel, it's on a supported platform
            _validate_wheel_platform_tags,
        ],
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
            # TODO: Don't consider md5_digest as good enough of satisifying the
            #       message digest requirement.
            not self.md5_digest.data
            and not self.sha256_digest.data
            and not self.blake2_256_digest.data
        ):
            raise wtforms.validators.ValidationError(
                "Include at least one message digest."
            )

        # Make sure that the filename extension is valid for the filetype
        _validate_filename_for_filetype(self.filename.data, self.filetype.data)
