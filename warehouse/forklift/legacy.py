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
import hashlib
import hmac
import os.path
import re
import tarfile
import tempfile
import zipfile

from cgi import FieldStorage, parse_header
from itertools import chain

import packaging.requirements
import packaging.specifiers
import packaging.utils
import packaging.version
import pkg_resources
import requests
import stdlib_list
import wtforms
import wtforms.validators

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPForbidden,
    HTTPGone,
    HTTPPermanentRedirect,
)
from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy import exists, func, orm
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from trove_classifiers import classifiers, deprecated_classifiers

from warehouse import forms
from warehouse.admin.flags import AdminFlagValue
from warehouse.admin.squats import Squat
from warehouse.classifiers.models import Classifier
from warehouse.metrics import IMetricsService
from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.models import (
    Dependency,
    DependencyKind,
    Description,
    File,
    Filename,
    JournalEntry,
    ProhibitedProjectName,
    Project,
    Release,
    Role,
)
from warehouse.packaging.tasks import update_bigquery_release_files
from warehouse.utils import http, readme

ONE_MB = 1 * 1024 * 1024
ONE_GB = 1 * 1024 * 1024 * 1024

MAX_FILESIZE = 100 * ONE_MB
MAX_SIGSIZE = 8 * 1024
MAX_PROJECT_SIZE = 10 * ONE_GB

PATH_HASHER = "blake2_256"


def namespace_stdlib_list(module_list):
    for module_name in module_list:
        parts = module_name.split(".")
        for i, part in enumerate(parts):
            yield ".".join(parts[: i + 1])


STDLIB_PROHIBITED = {
    packaging.utils.canonicalize_name(s.rstrip("-_.").lstrip("-_."))
    for s in chain.from_iterable(
        namespace_stdlib_list(stdlib_list.stdlib_list(version))
        for version in stdlib_list.short_versions
    )
}

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
_macosx_platform_re = re.compile(r"macosx_10_(\d+)+_(?P<arch>.*)")
_macosx_arches = {
    "ppc",
    "ppc64",
    "i386",
    "x86_64",
    "intel",
    "fat",
    "fat32",
    "fat64",
    "universal",
}


# Actual checking code;
def _valid_platform_tag(platform_tag):
    if platform_tag in _allowed_platforms:
        return True
    m = _macosx_platform_re.match(platform_tag)
    if m and m.group("arch") in _macosx_arches:
        return True
    return False


_error_message_order = ["metadata_version", "name", "version"]


_dist_file_re = re.compile(r".+?\.(tar\.gz|zip|whl|egg)$", re.I)


_wheel_file_re = re.compile(
    r"""
    ^
    (?P<namever>(?P<name>.+?)(-(?P<ver>\d.+?))?)
    (
        (-(?P<build>\d.*?))?
        -(?P<pyver>.+?)
        -(?P<abi>.+?)
        -(?P<plat>.+?)
        (?:\.whl|\.dist-info)
    )
    $
    """,
    re.VERBOSE,
)


_project_name_re = re.compile(
    r"^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$", re.IGNORECASE
)


_legacy_specifier_re = re.compile(r"^(?P<name>\S+)(?: \((?P<specifier>\S+)\))?$")


_valid_description_content_types = {"text/plain", "text/x-rst", "text/markdown"}

_valid_markdown_variants = {"CommonMark", "GFM"}


def _exc_with_message(exc, message, **kwargs):
    # The crappy old API that PyPI offered uses the status to pass down
    # messages to the client. So this function will make that easier to do.
    resp = exc(detail=message, **kwargs)
    resp.status = "{} {}".format(resp.status_code, message)
    return resp


def _validate_pep440_version(form, field):
    parsed = packaging.version.parse(field.data)

    # Check that this version is a valid PEP 440 version at all.
    if not isinstance(parsed, packaging.version.Version):
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
            "Invalid requirement: {!r}".format(requirement)
        ) from None

    if req.url is not None:
        raise wtforms.validators.ValidationError(
            "Can't direct dependency: {!r}".format(requirement)
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
            "Invalid requirement: {!r}.".format(requirement)
        ) from None

    if req.url is not None:
        raise wtforms.validators.ValidationError(
            "Can't have direct dependency: {!r}".format(requirement)
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
        label, url = value.split(", ", 1)
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

    content_type, parameters = parse_header(field.data)
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


def _construct_dependencies(form, types):
    for name, kind in types.items():
        for item in getattr(form, name).data:
            yield Dependency(kind=kind.value, specifier=item)


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
            wtforms.validators.DataRequired(),
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
            wtforms.validators.DataRequired(),
            wtforms.validators.Regexp(
                _project_name_re,
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
            wtforms.validators.DataRequired(),
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

    # File information
    pyversion = wtforms.StringField(validators=[wtforms.validators.Optional()])
    filetype = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.AnyOf(
                ["bdist_egg", "bdist_wheel", "sdist"], message="Use a known file type.",
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
        if not self.md5_digest.data and not self.sha256_digest.data:
            raise wtforms.validators.ValidationError(
                "Include at least one message digest."
            )


_safe_zipnames = re.compile(r"(purelib|platlib|headers|scripts|data).+", re.I)
# .tar uncompressed, .tar.gz .tgz, .tar.bz2 .tbz2
_tar_filenames_re = re.compile(r"\.(?:tar$|t(?:ar\.)?(?P<z_type>gz|bz2)$)")


def _is_valid_dist_file(filename, filetype):
    """
    Perform some basic checks to see whether the indicated file could be
    a valid distribution file.
    """

    # If our file is a zipfile, then ensure that it's members are only
    # compressed with supported compression methods.
    if zipfile.is_zipfile(filename):
        with zipfile.ZipFile(filename) as zfp:
            for zinfo in zfp.infolist():
                if zinfo.compress_type not in {
                    zipfile.ZIP_STORED,
                    zipfile.ZIP_DEFLATED,
                }:
                    return False

    tar_fn_match = _tar_filenames_re.search(filename)
    if tar_fn_match:
        # Ensure that this is a valid tar file, and that it contains PKG-INFO.
        z_type = tar_fn_match.group("z_type") or ""
        try:
            with tarfile.open(filename, f"r:{z_type}") as tar:
                # This decompresses the entire stream to validate it and the
                # tar within.  Easy CPU DoS attack. :/
                bad_tar = True
                member = tar.next()
                while member:
                    parts = os.path.split(member.name)
                    if len(parts) == 2 and parts[1] == "PKG-INFO":
                        bad_tar = False
                    member = tar.next()
                if bad_tar:
                    return False
        except tarfile.ReadError:
            return False
    elif filename.endswith(".exe"):
        # The only valid filetype for a .exe file is "bdist_wininst".
        if filetype != "bdist_wininst":
            return False

        # Ensure that the .exe is a valid zip file, and that all of the files
        # contained within it have safe filenames.
        try:
            with zipfile.ZipFile(filename, "r") as zfp:
                # We need the no branch below to work around a bug in
                # coverage.py where it's detecting a missed branch where there
                # isn't one.
                for zipname in zfp.namelist():  # pragma: no branch
                    if not _safe_zipnames.match(zipname):
                        return False
        except zipfile.BadZipFile:
            return False
    elif filename.endswith(".msi"):
        # The only valid filetype for a .msi is "bdist_msi"
        if filetype != "bdist_msi":
            return False

        # Check the first 8 bytes of the MSI file. This was taken from the
        # legacy implementation of PyPI which itself took it from the
        # implementation of `file` I believe.
        with open(filename, "rb") as fp:
            if fp.read(8) != b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1":
                return False
    elif filename.endswith(".zip") or filename.endswith(".egg"):
        # Ensure that the .zip/.egg is a valid zip file, and that it has a
        # PKG-INFO file.
        try:
            with zipfile.ZipFile(filename, "r") as zfp:
                for zipname in zfp.namelist():
                    parts = os.path.split(zipname)
                    if len(parts) == 2 and parts[1] == "PKG-INFO":
                        # We need the no branch below to work around a bug in
                        # coverage.py where it's detecting a missed branch
                        # where there isn't one.
                        break  # pragma: no branch
                else:
                    return False
        except zipfile.BadZipFile:
            return False
    elif filename.endswith(".whl"):
        # Ensure that the .whl is a valid zip file, and that it has a WHEEL
        # file.
        try:
            with zipfile.ZipFile(filename, "r") as zfp:
                for zipname in zfp.namelist():
                    parts = os.path.split(zipname)
                    if len(parts) == 2 and parts[1] == "WHEEL":
                        # We need the no branch below to work around a bug in
                        # coverage.py where it's detecting a missed branch
                        # where there isn't one.
                        break  # pragma: no branch
                else:
                    return False
        except zipfile.BadZipFile:
            return False

    # If we haven't yet decided it's not valid, then we'll assume it is and
    # allow it.
    return True


def _is_duplicate_file(db_session, filename, hashes):
    """
    Check to see if file already exists, and if it's content matches.
    A file is considered to exist if its filename *or* blake2 digest are
    present in a file row in the database.

    Returns:
    - True: This file is a duplicate and all further processing should halt.
    - False: This file exists, but it is not a duplicate.
    - None: This file does not exist.
    """

    file_ = (
        db_session.query(File)
        .filter(
            (File.filename == filename)
            | (File.blake2_256_digest == hashes["blake2_256"])
        )
        .first()
    )

    if file_ is not None:
        return (
            file_.filename == filename
            and file_.sha256_digest == hashes["sha256"]
            and file_.md5_digest == hashes["md5"]
            and file_.blake2_256_digest == hashes["blake2_256"]
        )

    return None


@view_config(
    route_name="forklift.legacy.file_upload",
    uses_session=True,
    require_csrf=False,
    require_methods=["POST"],
    has_translations=True,
)
def file_upload(request):
    # If we're in read-only mode, let upload clients know
    if request.flags.enabled(AdminFlagValue.READ_ONLY):
        raise _exc_with_message(
            HTTPForbidden, "Read-only mode: Uploads are temporarily disabled."
        )

    if request.flags.enabled(AdminFlagValue.DISALLOW_NEW_UPLOAD):
        raise _exc_with_message(
            HTTPForbidden,
            "New uploads are temporarily disabled. "
            "See {projecthelp} for more information.".format(
                projecthelp=request.help_url(_anchor="admin-intervention")
            ),
        )

    # Log an attempt to upload
    metrics = request.find_service(IMetricsService, context=None)
    metrics.increment("warehouse.upload.attempt")

    # Before we do anything, if there isn't an authenticated user with this
    # request, then we'll go ahead and bomb out.
    if request.authenticated_userid is None:
        raise _exc_with_message(
            HTTPForbidden,
            "Invalid or non-existent authentication information. "
            "See {projecthelp} for more information.".format(
                projecthelp=request.help_url(_anchor="invalid-auth")
            ),
        )

    # Ensure that user has a verified, primary email address. This should both
    # reduce the ease of spam account creation and activity, as well as act as
    # a forcing function for https://github.com/pypa/warehouse/issues/3632.
    # TODO: Once https://github.com/pypa/warehouse/issues/3632 has been solved,
    #       we might consider a different condition, possibly looking at
    #       User.is_active instead.
    if not (request.user.primary_email and request.user.primary_email.verified):
        raise _exc_with_message(
            HTTPBadRequest,
            (
                "User {!r} does not have a verified primary email address. "
                "Please add a verified primary email before attempting to "
                "upload to PyPI. See {project_help} for more information."
            ).format(
                request.user.username,
                project_help=request.help_url(_anchor="verified-email"),
            ),
        ) from None

    # Do some cleanup of the various form fields
    for key in list(request.POST):
        value = request.POST.get(key)
        if isinstance(value, str):
            # distutils "helpfully" substitutes unknown, but "required" values
            # with the string "UNKNOWN". This is basically never what anyone
            # actually wants so we'll just go ahead and delete anything whose
            # value is UNKNOWN.
            if value.strip() == "UNKNOWN":
                del request.POST[key]

            # Escape NUL characters, which psycopg doesn't like
            if "\x00" in value:
                request.POST[key] = value.replace("\x00", "\\x00")

    # We require protocol_version 1, it's the only supported version however
    # passing a different version should raise an error.
    if request.POST.get("protocol_version", "1") != "1":
        raise _exc_with_message(HTTPBadRequest, "Unknown protocol version.")

    # Check if any fields were supplied as a tuple and have become a
    # FieldStorage. The 'content' and 'gpg_signature' fields _should_ be a
    # FieldStorage, however.
    # ref: https://github.com/pypa/warehouse/issues/2185
    # ref: https://github.com/pypa/warehouse/issues/2491
    for field in set(request.POST) - {"content", "gpg_signature"}:
        values = request.POST.getall(field)
        if any(isinstance(value, FieldStorage) for value in values):
            raise _exc_with_message(HTTPBadRequest, f"{field}: Should not be a tuple.")

    # Validate and process the incoming metadata.
    form = MetadataForm(request.POST)

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
                        value=field.data, field=field.description
                    )
                    + "Error: {} ".format(form.errors[field_name][0])
                    + "See "
                    "https://packaging.python.org/specifications/core-metadata"
                    + " for more information."
                )
            else:
                error_message = "Invalid value for {field}. Error: {msgs[0]}".format(
                    field=field_name, msgs=form.errors[field_name]
                )
        else:
            error_message = "Error: {}".format(form.errors[field_name][0])

        raise _exc_with_message(HTTPBadRequest, error_message)

    # Ensure that we have file data in the request.
    if "content" not in request.POST:
        raise _exc_with_message(HTTPBadRequest, "Upload payload does not have a file.")

    # Look up the project first before doing anything else, this is so we can
    # automatically register it if we need to and can check permissions before
    # going any further.
    try:
        project = (
            request.db.query(Project)
            .filter(
                Project.normalized_name == func.normalize_pep426_name(form.name.data)
            )
            .one()
        )
    except NoResultFound:
        # Check for AdminFlag set by a PyPI Administrator disabling new project
        # registration, reasons for this include Spammers, security
        # vulnerabilities, or just wanting to be lazy and not worry ;)
        if request.flags.enabled(AdminFlagValue.DISALLOW_NEW_PROJECT_REGISTRATION):
            raise _exc_with_message(
                HTTPForbidden,
                (
                    "New project registration temporarily disabled. "
                    "See {projecthelp} for more information."
                ).format(projecthelp=request.help_url(_anchor="admin-intervention")),
            ) from None

        # Before we create the project, we're going to check our prohibited names to
        # see if this project is even allowed to be registered. If it is not,
        # then we're going to deny the request to create this project.
        if request.db.query(
            exists().where(
                ProhibitedProjectName.name == func.normalize_pep426_name(form.name.data)
            )
        ).scalar():
            raise _exc_with_message(
                HTTPBadRequest,
                (
                    "The name {name!r} isn't allowed. "
                    "See {projecthelp} for more information."
                ).format(
                    name=form.name.data,
                    projecthelp=request.help_url(_anchor="project-name"),
                ),
            ) from None

        # Also check for collisions with Python Standard Library modules.
        if packaging.utils.canonicalize_name(form.name.data) in STDLIB_PROHIBITED:
            raise _exc_with_message(
                HTTPBadRequest,
                (
                    "The name {name!r} isn't allowed (conflict with Python "
                    "Standard Library module name). See "
                    "{projecthelp} for more information."
                ).format(
                    name=form.name.data,
                    projecthelp=request.help_url(_anchor="project-name"),
                ),
            ) from None

        # The project doesn't exist in our database, so first we'll check for
        # projects with a similar name
        squattees = (
            request.db.query(Project)
            .filter(
                func.levenshtein(
                    Project.normalized_name, func.normalize_pep426_name(form.name.data)
                )
                <= 2
            )
            .all()
        )

        # Next we'll create the project
        project = Project(name=form.name.data)
        request.db.add(project)

        # Now that the project exists, add any squats which it is the squatter for
        for squattee in squattees:
            request.db.add(Squat(squatter=project, squattee=squattee))

        # Then we'll add a role setting the current user as the "Owner" of the
        # project.
        request.db.add(Role(user=request.user, project=project, role_name="Owner"))
        # TODO: This should be handled by some sort of database trigger or a
        #       SQLAlchemy hook or the like instead of doing it inline in this
        #       view.
        request.db.add(
            JournalEntry(
                name=project.name,
                action="create",
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            )
        )
        request.db.add(
            JournalEntry(
                name=project.name,
                action="add Owner {}".format(request.user.username),
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            )
        )

        project.record_event(
            tag="project:create",
            ip_address=request.remote_addr,
            additional={"created_by": request.user.username},
        )
        project.record_event(
            tag="project:role:add",
            ip_address=request.remote_addr,
            additional={
                "submitted_by": request.user.username,
                "role_name": "Owner",
                "target_user": request.user.username,
            },
        )

    # Check that the user has permission to do things to this project, if this
    # is a new project this will act as a sanity check for the role we just
    # added above.
    allowed = request.has_permission("upload", project)
    if not allowed:
        reason = getattr(allowed, "reason", None)
        msg = (
            (
                "The user '{0}' isn't allowed to upload to project '{1}'. "
                "See {2} for more information."
            ).format(
                request.user.username,
                project.name,
                request.help_url(_anchor="project-name"),
            )
            if reason is None
            else allowed.msg
        )
        raise _exc_with_message(HTTPForbidden, msg)

    # Update name if it differs but is still equivalent. We don't need to check if
    # they are equivalent when normalized because that's already been done when we
    # queried for the project.
    if project.name != form.name.data:
        project.name = form.name.data

    # Render our description so we can save from having to render this data every time
    # we load a project description page.
    rendered = None
    if form.description.data:
        description_content_type = form.description_content_type.data
        if not description_content_type:
            description_content_type = "text/x-rst"

        rendered = readme.render(
            form.description.data, description_content_type, use_fallback=False
        )

        # Uploading should prevent broken rendered descriptions.
        if rendered is None:
            if form.description_content_type.data:
                message = (
                    "The description failed to render "
                    "for '{description_content_type}'."
                ).format(description_content_type=description_content_type)
            else:
                message = (
                    "The description failed to render "
                    "in the default format of reStructuredText."
                )
            raise _exc_with_message(
                HTTPBadRequest,
                "{message} See {projecthelp} for more information.".format(
                    message=message,
                    projecthelp=request.help_url(_anchor="description-content-type"),
                ),
            ) from None

    try:
        canonical_version = packaging.utils.canonicalize_version(form.version.data)
        release = (
            request.db.query(Release)
            .filter(
                (Release.project == project)
                & (Release.canonical_version == canonical_version)
            )
            .one()
        )
    except MultipleResultsFound:
        # There are multiple releases of this project which have the same
        # canonical version that were uploaded before we checked for
        # canonical version equivalence, so return the exact match instead
        release = (
            request.db.query(Release)
            .filter(
                (Release.project == project) & (Release.version == form.version.data)
            )
            .one()
        )
    except NoResultFound:
        # Look up all of the valid classifiers
        all_classifiers = request.db.query(Classifier).all()

        # Get all the classifiers for this release
        release_classifiers = [
            c for c in all_classifiers if c.classifier in form.classifiers.data
        ]

        # Determine if we need to add any new classifiers to the database
        missing_classifiers = set(form.classifiers.data or []) - set(
            c.classifier for c in release_classifiers
        )

        # Add any new classifiers to the database
        if missing_classifiers:
            for missing_classifier_name in missing_classifiers:
                missing_classifier = Classifier(classifier=missing_classifier_name)
                request.db.add(missing_classifier)
                release_classifiers.append(missing_classifier)

        release = Release(
            project=project,
            _classifiers=release_classifiers,
            dependencies=list(
                _construct_dependencies(
                    form,
                    {
                        "requires": DependencyKind.requires,
                        "provides": DependencyKind.provides,
                        "obsoletes": DependencyKind.obsoletes,
                        "requires_dist": DependencyKind.requires_dist,
                        "provides_dist": DependencyKind.provides_dist,
                        "obsoletes_dist": DependencyKind.obsoletes_dist,
                        "requires_external": DependencyKind.requires_external,
                        "project_urls": DependencyKind.project_url,
                    },
                )
            ),
            canonical_version=canonical_version,
            description=Description(
                content_type=form.description_content_type.data,
                raw=form.description.data or "",
                html=rendered or "",
                rendered_by=readme.renderer_version(),
            ),
            **{
                k: getattr(form, k).data
                for k in {
                    # This is a list of all the fields in the form that we
                    # should pull off and insert into our new release.
                    "version",
                    "summary",
                    "license",
                    "author",
                    "author_email",
                    "maintainer",
                    "maintainer_email",
                    "keywords",
                    "platform",
                    "home_page",
                    "download_url",
                    "requires_python",
                }
            },
            uploader=request.user,
            uploaded_via=request.user_agent,
        )
        request.db.add(release)
        # TODO: This should be handled by some sort of database trigger or
        #       a SQLAlchemy hook or the like instead of doing it inline in
        #       this view.
        request.db.add(
            JournalEntry(
                name=release.project.name,
                version=release.version,
                action="new release",
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            )
        )

        project.record_event(
            tag="project:release:add",
            ip_address=request.remote_addr,
            additional={
                "submitted_by": request.user.username,
                "canonical_version": release.canonical_version,
            },
        )

    # TODO: We need a better solution to this than to just do it inline inside
    #       this method. Ideally the version field would just be sortable, but
    #       at least this should be some sort of hook or trigger.
    releases = (
        request.db.query(Release)
        .filter(Release.project == project)
        .options(
            orm.load_only(Release.project_id, Release.version, Release._pypi_ordering)
        )
        .all()
    )
    for i, r in enumerate(
        sorted(releases, key=lambda x: packaging.version.parse(x.version))
    ):
        r._pypi_ordering = i

    # Pull the filename out of our POST data.
    filename = request.POST["content"].filename

    # Make sure that the filename does not contain any path separators.
    if "/" in filename or "\\" in filename:
        raise _exc_with_message(
            HTTPBadRequest, "Cannot upload a file with '/' or '\\' in the name."
        )

    # Make sure the filename ends with an allowed extension.
    if _dist_file_re.search(filename) is None:
        raise _exc_with_message(
            HTTPBadRequest,
            "Invalid file extension: Use .egg, .tar.gz, .whl or .zip "
            "extension. See https://www.python.org/dev/peps/pep-0527 "
            "for more information.",
        )

    # Make sure that our filename matches the project that it is being uploaded
    # to.
    prefix = pkg_resources.safe_name(project.name).lower()
    if not pkg_resources.safe_name(filename).lower().startswith(prefix):
        raise _exc_with_message(
            HTTPBadRequest,
            "Start filename for {!r} with {!r}.".format(project.name, prefix),
        )

    # Check the content type of what is being uploaded
    if not request.POST["content"].type or request.POST["content"].type.startswith(
        "image/"
    ):
        raise _exc_with_message(HTTPBadRequest, "Invalid distribution file.")

    # The project may or may not have a file size specified on the project, if
    # it does then it may or may not be smaller or larger than our global file
    # size limits.
    file_size_limit = max(filter(None, [MAX_FILESIZE, project.upload_limit]))
    project_size_limit = max(filter(None, [MAX_PROJECT_SIZE, project.total_size_limit]))

    file_data = None
    with tempfile.TemporaryDirectory() as tmpdir:
        temporary_filename = os.path.join(tmpdir, filename)

        # Buffer the entire file onto disk, checking the hash of the file as we
        # go along.
        with open(temporary_filename, "wb") as fp:
            file_size = 0
            file_hashes = {
                "md5": hashlib.md5(),
                "sha256": hashlib.sha256(),
                "blake2_256": hashlib.blake2b(digest_size=256 // 8),
            }
            for chunk in iter(lambda: request.POST["content"].file.read(8096), b""):
                file_size += len(chunk)
                if file_size > file_size_limit:
                    raise _exc_with_message(
                        HTTPBadRequest,
                        "File too large. "
                        + "Limit for project {name!r} is {limit} MB. ".format(
                            name=project.name, limit=file_size_limit // ONE_MB
                        )
                        + "See "
                        + request.help_url(_anchor="file-size-limit")
                        + " for more information.",
                    )
                if file_size + project.total_size > project_size_limit:
                    raise _exc_with_message(
                        HTTPBadRequest,
                        "Project size too large. Limit for "
                        + "project {name!r} total size is {limit} GB. ".format(
                            name=project.name, limit=project_size_limit // ONE_GB,
                        )
                        + "See "
                        + request.help_url(_anchor="project-size-limit"),
                    )
                fp.write(chunk)
                for hasher in file_hashes.values():
                    hasher.update(chunk)

        # Take our hash functions and compute the final hashes for them now.
        file_hashes = {k: h.hexdigest().lower() for k, h in file_hashes.items()}

        # Actually verify the digests that we've gotten. We're going to use
        # hmac.compare_digest even though we probably don't actually need to
        # because it's better safe than sorry. In the case of multiple digests
        # we expect them all to be given.
        if not all(
            [
                hmac.compare_digest(
                    getattr(form, "{}_digest".format(digest_name)).data.lower(),
                    digest_value,
                )
                for digest_name, digest_value in file_hashes.items()
                if getattr(form, "{}_digest".format(digest_name)).data
            ]
        ):
            raise _exc_with_message(
                HTTPBadRequest,
                "The digest supplied does not match a digest calculated "
                "from the uploaded file.",
            )

        # Check to see if the file that was uploaded exists already or not.
        is_duplicate = _is_duplicate_file(request.db, filename, file_hashes)
        if is_duplicate:
            return Response()
        elif is_duplicate is not None:
            raise _exc_with_message(
                HTTPBadRequest,
                # Note: Changing this error message to something that doesn't
                # start with "File already exists" will break the
                # --skip-existing functionality in twine
                # ref: https://github.com/pypa/warehouse/issues/3482
                # ref: https://github.com/pypa/twine/issues/332
                "File already exists. See "
                + request.help_url(_anchor="file-name-reuse")
                + " for more information.",
            )

        # Check to see if the file that was uploaded exists in our filename log
        if request.db.query(
            request.db.query(Filename).filter(Filename.filename == filename).exists()
        ).scalar():
            raise _exc_with_message(
                HTTPBadRequest,
                "This filename has already been used, use a "
                "different version. "
                "See "
                + request.help_url(_anchor="file-name-reuse")
                + " for more information.",
            )

        # Check to see if uploading this file would create a duplicate sdist
        # for the current release.
        if (
            form.filetype.data == "sdist"
            and request.db.query(
                request.db.query(File)
                .filter((File.release == release) & (File.packagetype == "sdist"))
                .exists()
            ).scalar()
        ):
            raise _exc_with_message(
                HTTPBadRequest, "Only one sdist may be uploaded per release."
            )

        # Check the file to make sure it is a valid distribution file.
        if not _is_valid_dist_file(temporary_filename, form.filetype.data):
            raise _exc_with_message(HTTPBadRequest, "Invalid distribution file.")

        # Check that if it's a binary wheel, it's on a supported platform
        if filename.endswith(".whl"):
            wheel_info = _wheel_file_re.match(filename)
            plats = wheel_info.group("plat").split(".")
            for plat in plats:
                if not _valid_platform_tag(plat):
                    raise _exc_with_message(
                        HTTPBadRequest,
                        "Binary wheel '{filename}' has an unsupported "
                        "platform tag '{plat}'.".format(filename=filename, plat=plat),
                    )

        # Also buffer the entire signature file to disk.
        if "gpg_signature" in request.POST:
            has_signature = True
            with open(os.path.join(tmpdir, filename + ".asc"), "wb") as fp:
                signature_size = 0
                for chunk in iter(
                    lambda: request.POST["gpg_signature"].file.read(8096), b""
                ):
                    signature_size += len(chunk)
                    if signature_size > MAX_SIGSIZE:
                        raise _exc_with_message(HTTPBadRequest, "Signature too large.")
                    fp.write(chunk)

            # Check whether signature is ASCII armored
            with open(os.path.join(tmpdir, filename + ".asc"), "rb") as fp:
                if not fp.read().startswith(b"-----BEGIN PGP SIGNATURE-----"):
                    raise _exc_with_message(
                        HTTPBadRequest, "PGP signature isn't ASCII armored."
                    )
        else:
            has_signature = False

        # TODO: This should be handled by some sort of database trigger or a
        #       SQLAlchemy hook or the like instead of doing it inline in this
        #       view.
        request.db.add(Filename(filename=filename))

        # Store the information about the file in the database.
        file_ = File(
            release=release,
            filename=filename,
            python_version=form.pyversion.data,
            packagetype=form.filetype.data,
            comment_text=form.comment.data,
            size=file_size,
            has_signature=bool(has_signature),
            md5_digest=file_hashes["md5"],
            sha256_digest=file_hashes["sha256"],
            blake2_256_digest=file_hashes["blake2_256"],
            # Figure out what our filepath is going to be, we're going to use a
            # directory structure based on the hash of the file contents. This
            # will ensure that the contents of the file cannot change without
            # it also changing the path that the file is saved too.
            path="/".join(
                [
                    file_hashes[PATH_HASHER][:2],
                    file_hashes[PATH_HASHER][2:4],
                    file_hashes[PATH_HASHER][4:],
                    filename,
                ]
            ),
            uploaded_via=request.user_agent,
        )
        file_data = file_
        request.db.add(file_)

        # TODO: This should be handled by some sort of database trigger or a
        #       SQLAlchemy hook or the like instead of doing it inline in this
        #       view.
        request.db.add(
            JournalEntry(
                name=release.project.name,
                version=release.version,
                action="add {python_version} file {filename}".format(
                    python_version=file_.python_version, filename=file_.filename
                ),
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            )
        )

        # TODO: We need a better answer about how to make this transactional so
        #       this won't take affect until after a commit has happened, for
        #       now we'll just ignore it and save it before the transaction is
        #       committed.
        storage = request.find_service(IFileStorage)
        storage.store(
            file_.path,
            os.path.join(tmpdir, filename),
            meta={
                "project": file_.release.project.normalized_name,
                "version": file_.release.version,
                "package-type": file_.packagetype,
                "python-version": file_.python_version,
            },
        )
        if has_signature:
            storage.store(
                file_.pgp_path,
                os.path.join(tmpdir, filename + ".asc"),
                meta={
                    "project": file_.release.project.normalized_name,
                    "version": file_.release.version,
                    "package-type": file_.packagetype,
                    "python-version": file_.python_version,
                },
            )

    # We are flushing the database requests so that we
    # can access the server default values when initiating celery
    # tasks.
    request.db.flush()

    # Push updates to BigQuery
    dist_metadata = {
        "metadata_version": form["metadata_version"].data,
        "name": form["name"].data,
        "version": form["version"].data,
        "summary": form["summary"].data,
        "description": form["description"].data,
        "author": form["author"].data,
        "description_content_type": form["description_content_type"].data,
        "author_email": form["author_email"].data,
        "maintainer": form["maintainer"].data,
        "maintainer_email": form["maintainer_email"].data,
        "license": form["license"].data,
        "keywords": form["keywords"].data,
        "classifiers": form["classifiers"].data,
        "platform": form["platform"].data,
        "home_page": form["home_page"].data,
        "download_url": form["download_url"].data,
        "requires_python": form["requires_python"].data,
        "pyversion": form["pyversion"].data,
        "filetype": form["filetype"].data,
        "comment": form["comment"].data,
        "requires": form["requires"].data,
        "provides": form["provides"].data,
        "obsoletes": form["obsoletes"].data,
        "requires_dist": form["requires_dist"].data,
        "provides_dist": form["provides_dist"].data,
        "obsoletes_dist": form["obsoletes_dist"].data,
        "requires_external": form["requires_external"].data,
        "project_urls": form["project_urls"].data,
        "filename": file_data.filename,
        "python_version": file_data.python_version,
        "packagetype": file_data.packagetype,
        "comment_text": file_data.comment_text,
        "size": file_data.size,
        "has_signature": file_data.has_signature,
        "md5_digest": file_data.md5_digest,
        "sha256_digest": file_data.sha256_digest,
        "blake2_256_digest": file_data.blake2_256_digest,
        "path": file_data.path,
        "uploaded_via": file_data.uploaded_via,
        "upload_time": file_data.upload_time,
    }
    if not request.registry.settings.get("warehouse.release_files_table") is None:
        request.task(update_bigquery_release_files).delay(dist_metadata)

    # Log a successful upload
    metrics.increment("warehouse.upload.ok", tags=[f"filetype:{form.filetype.data}"])

    return Response()


def _legacy_purge(status, *args, **kwargs):
    if status:
        requests.post(*args, **kwargs)


@view_config(
    route_name="forklift.legacy.submit", require_csrf=False, require_methods=["POST"]
)
@view_config(
    route_name="forklift.legacy.submit_pkg_info",
    require_csrf=False,
    require_methods=["POST"],
)
def submit(request):
    return _exc_with_message(
        HTTPGone,
        (
            "Project pre-registration is no longer required or supported, "
            "upload your files instead."
        ),
    )


@view_config(
    route_name="forklift.legacy.doc_upload",
    require_csrf=False,
    require_methods=["POST"],
)
def doc_upload(request):
    return _exc_with_message(
        HTTPGone,
        "Uploading documentation is no longer supported, we recommend using "
        "https://readthedocs.org/.",
    )


@view_config(
    route_name="forklift.legacy.missing_trailing_slash",
    require_csrf=False,
    require_methods=["POST"],
)
def missing_trailing_slash_redirect(request):
    """
    Redirect requests to /legacy to the correct /legacy/ route with a
    HTTP-308 Permanent Redirect
    """
    return _exc_with_message(
        HTTPPermanentRedirect,
        "An upload was attempted to /legacy but the expected upload URL is "
        "/legacy/ (with a trailing slash)",
        location=request.route_path("forklift.legacy.file_upload"),
    )
