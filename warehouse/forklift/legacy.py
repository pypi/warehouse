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
import tempfile
import zipfile
from cgi import parse_header

from cgi import FieldStorage
from itertools import chain

import packaging.specifiers
import packaging.requirements
import packaging.utils
import packaging.version
import pkg_resources
import requests
import stdlib_list
import wtforms
import wtforms.validators

from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden, HTTPGone
from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy import exists, func, orm
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound

from warehouse import forms
from warehouse.classifiers.models import Classifier
from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.models import (
    Project, Release, Dependency, DependencyKind, Role, File, Filename,
    JournalEntry, BlacklistedProject,
)
from warehouse.utils import http


MAX_FILESIZE = 60 * 1024 * 1024  # 60M
MAX_SIGSIZE = 8 * 1024           # 8K

PATH_HASHER = "blake2_256"


def namespace_stdlib_list(module_list):
    for module_name in module_list:
        parts = module_name.split('.')
        for i, part in enumerate(parts):
            yield '.'.join(parts[:i + 1])


STDLIB_PROHIBITTED = {
    packaging.utils.canonicalize_name(s.rstrip('-_.').lstrip('-_.'))
    for s in chain.from_iterable(
        namespace_stdlib_list(stdlib_list.stdlib_list(version))
        for version in stdlib_list.short_versions)
}

# Wheel platform checking
# These platforms can be handled by a simple static list:
_allowed_platforms = {
    "any",
    "win32", "win_amd64", "win_ia64",
    "manylinux1_x86_64", "manylinux1_i686",
    "linux_armv6l", "linux_armv7l",
}
# macosx is a little more complicated:
_macosx_platform_re = re.compile("macosx_10_(\d+)+_(?P<arch>.*)")
_macosx_arches = {
    "ppc", "ppc64",
    "i386", "x86_64",
    "intel", "fat", "fat32", "fat64", "universal",
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


_dist_file_regexes = {
    # True/False is for legacy or not.
    True: re.compile(
        r".+?\.(exe|tar\.gz|bz2|rpm|deb|zip|tgz|egg|dmg|msi|whl)$",
        re.I,
    ),
    False: re.compile(r".+?\.(tar\.gz|zip|whl|egg)$", re.I),
}


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
    r"^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$",
    re.IGNORECASE,
)


_legacy_specifier_re = re.compile(
    r"^(?P<name>\S+)(?: \((?P<specifier>\S+)\))?$"
)


_valid_description_content_types = {
    'text/plain',
    'text/x-rst',
    'text/markdown',
}

_valid_markdown_variants = {
    'CommonMark',
    'GFM',
}


def _exc_with_message(exc, message):
    # The crappy old API that PyPI offered uses the status to pass down
    # messages to the client. So this function will make that easier to do.
    resp = exc(message)
    resp.status = "{} {}".format(resp.status_code, message)
    return resp


def _validate_pep440_version(form, field):
    parsed = packaging.version.parse(field.data)

    # Check that this version is a valid PEP 440 version at all.
    if not isinstance(parsed, packaging.version.Version):
        raise wtforms.validators.ValidationError(
            "Must start and end with a letter or numeral and contain only "
            "ascii numeric and '.', '_' and '-'."
        )

    # Check that this version does not have a PEP 440 local segment attached
    # to it.
    if parsed.local is not None:
        raise wtforms.validators.ValidationError(
            "Cannot use PEP 440 local versions."
        )


def _parse_legacy_requirement(requirement):
    parsed = _legacy_specifier_re.search(requirement)
    if parsed is None:
        raise ValueError("Invalid Requirement.")
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
            "Cannot use direct dependency: {!r}".format(requirement)
        )

    if not req.name.isalnum() or req.name[0].isdigit():
        raise wtforms.validators.ValidationError(
            "Must be a valid Python identifier."
        )


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
            "Cannot have direct dependency: {!r}".format(requirement)
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
            "Must have both a label and an URL.",
        ) from None

    if not label:
        raise wtforms.validators.ValidationError("Must have a label.")

    if len(label) > 32:
        raise wtforms.validators.ValidationError(
            "Label must not be longer than 32 characters."
        )

    if not url:
        raise wtforms.validators.ValidationError("Must have an URL.")

    if not http.is_valid_uri(url, require_authority=False):
        raise wtforms.validators.ValidationError("Invalid URL.")


def _validate_project_url_list(form, field):
    for datum in field.data:
        _validate_project_url(datum)


def _validate_rfc822_email_field(form, field):
    email_validator = wtforms.validators.Email(message='Invalid email address')
    addresses = email.utils.getaddresses([field.data])

    for real_name, address in addresses:
        email_validator(form, type('field', (), {'data': address}))


def _validate_description_content_type(form, field):
    def _raise(message):
        raise wtforms.validators.ValidationError(
            f"Invalid description content type: {message}"
        )

    content_type, parameters = parse_header(field.data)
    if content_type not in _valid_description_content_types:
        _raise("type/subtype is not valid")

    charset = parameters.get('charset')
    if charset and charset != 'UTF-8':
        _raise("charset is not valid")

    variant = parameters.get('variant')
    if (content_type == 'text/markdown' and variant and
            variant not in _valid_markdown_variants):
        _raise(
            "variant is not valid, expected one of {}".format(
                ', '.join(_valid_markdown_variants)))


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
                message="Unknown Metadata Version",
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
                    "Must start and end with a letter or numeral and contain "
                    "only ascii numeric and '.', '_' and '-'."
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
                message="Cannot have leading or trailing whitespace.",
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
                message="Multiple lines are not allowed.",
            )
        ],
    )
    description = wtforms.StringField(
        description="Description",
        validators=[wtforms.validators.Optional()],
    )
    author = wtforms.StringField(
        description="Author",
        validators=[wtforms.validators.Optional()],
    )
    description_content_type = wtforms.StringField(
        description="Description-Content-Type",
        validators=[
            wtforms.validators.Optional(),
            _validate_description_content_type,
        ],
    )
    author_email = wtforms.StringField(
        description="Author-email",
        validators=[
            wtforms.validators.Optional(),
            _validate_rfc822_email_field,
        ],
    )
    maintainer = wtforms.StringField(
        description="Maintainer",
        validators=[wtforms.validators.Optional()],
    )
    maintainer_email = wtforms.StringField(
        description="Maintainer-email",
        validators=[
            wtforms.validators.Optional(),
            _validate_rfc822_email_field,
        ],
    )
    license = wtforms.StringField(
        description="License",
        validators=[wtforms.validators.Optional()],
    )
    keywords = wtforms.StringField(
        description="Keywords",
        validators=[wtforms.validators.Optional()],
    )
    classifiers = wtforms.fields.SelectMultipleField(
        description="Classifier",
    )
    platform = wtforms.StringField(
        description="Platform",
        validators=[wtforms.validators.Optional()],
    )

    # URLs
    home_page = wtforms.StringField(
        description="Home-Page",
        validators=[
            wtforms.validators.Optional(),
            forms.URIValidator(),
        ],
    )
    download_url = wtforms.StringField(
        description="Download-URL",
        validators=[
            wtforms.validators.Optional(),
            forms.URIValidator(),
        ],
    )

    # Dependency Information
    requires_python = wtforms.StringField(
        description="Requires-Python",
        validators=[
            wtforms.validators.Optional(),
            _validate_pep440_specifier_field,
        ],
    )

    # File information
    pyversion = wtforms.StringField(
        validators=[wtforms.validators.Optional()],
    )
    filetype = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.AnyOf(
                [
                    "bdist_dmg", "bdist_dumb", "bdist_egg", "bdist_msi",
                    "bdist_rpm", "bdist_wheel", "bdist_wininst", "sdist",
                ],
                message="Unknown type of file.",
            ),
        ]
    )
    comment = wtforms.StringField(
        validators=[wtforms.validators.Optional()],
    )
    md5_digest = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
        ],
    )
    sha256_digest = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
            wtforms.validators.Regexp(
                r"^[A-F0-9]{64}$",
                re.IGNORECASE,
                message="Must be a valid, hex encoded, SHA256 message digest.",
            ),
        ],
    )
    blake2_256_digest = wtforms.StringField(
        validators=[
            wtforms.validators.Optional(),
            wtforms.validators.Regexp(
                r"^[A-F0-9]{64}$",
                re.IGNORECASE,
                message="Must be a valid, hex encoded, blake2 message digest.",
            ),
        ],
    )

    # Legacy dependency information
    requires = ListField(
        validators=[
            wtforms.validators.Optional(),
            _validate_legacy_non_dist_req_list,
        ],
    )
    provides = ListField(
        validators=[
            wtforms.validators.Optional(),
            _validate_legacy_non_dist_req_list,
        ],
    )
    obsoletes = ListField(
        validators=[
            wtforms.validators.Optional(),
            _validate_legacy_non_dist_req_list,
        ],
    )

    # Newer dependency information
    requires_dist = ListField(
        description="Requires-Dist",
        validators=[
            wtforms.validators.Optional(),
            _validate_legacy_dist_req_list,
        ],
    )
    provides_dist = ListField(
        description="Provides-Dist",
        validators=[
            wtforms.validators.Optional(),
            _validate_legacy_dist_req_list,
        ],
    )
    obsoletes_dist = ListField(
        description="Obsoletes-Dist",
        validators=[
            wtforms.validators.Optional(),
            _validate_legacy_dist_req_list,
        ],
    )
    requires_external = ListField(
        description="Requires-External",
        validators=[
            wtforms.validators.Optional(),
            _validate_requires_external_list,
        ],
    )

    # Newer metadata information
    project_urls = ListField(
        description="Project-URL",
        validators=[
            wtforms.validators.Optional(),
            _validate_project_url_list,
        ],
    )

    def full_validate(self):
        # All non source releases *must* have a pyversion
        if (self.filetype.data and
                self.filetype.data != "sdist" and not self.pyversion.data):
            raise wtforms.validators.ValidationError(
                "Python version is required for binary distribution uploads."
            )

        # All source releases *must* have a pyversion of "source"
        if self.filetype.data == "sdist":
            if not self.pyversion.data:
                self.pyversion.data = "source"
            elif self.pyversion.data != "source":
                raise wtforms.validators.ValidationError(
                    "The only valid Python version for a sdist is 'source'."
                )

        # We *must* have at least one digest to verify against.
        if not self.md5_digest.data and not self.sha256_digest.data:
            raise wtforms.validators.ValidationError(
                "Must include at least one message digest.",
            )


_safe_zipnames = re.compile(r"(purelib|platlib|headers|scripts|data).+", re.I)


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
                if zinfo.compress_type not in {zipfile.ZIP_STORED,
                                               zipfile.ZIP_DEFLATED}:
                    return False

    if filename.endswith(".exe"):
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
                        (File.filename == filename) |
                        (File.blake2_256_digest == hashes["blake2_256"]))
                  .first()
    )

    if file_ is not None:
        return (
            file_.filename == filename and
            file_.sha256_digest == hashes["sha256"] and
            file_.md5_digest == hashes["md5"] and
            file_.blake2_256_digest == hashes["blake2_256"]
        )

    return None


def _no_deprecated_classifiers(request):
    deprecated_classifiers = {
        classifier.classifier
        for classifier in (
            request.db.query(Classifier.classifier)
            .filter(Classifier.deprecated.is_(True))
            .all()
        )
    }

    def validate_no_deprecated_classifiers(form, field):
        invalid_classifiers = set(field.data or []) & deprecated_classifiers
        if invalid_classifiers:
            first_invalid_classifier = sorted(invalid_classifiers)[0]
            host = request.registry.settings.get("warehouse.domain")
            classifiers_url = request.route_url('classifiers', _host=host)

            raise wtforms.validators.ValidationError(
                f'Classifier {first_invalid_classifier!r} has been '
                f'deprecated, see {classifiers_url} for a list of valid '
                'classifiers.'
            )

    return validate_no_deprecated_classifiers


@view_config(
    route_name="forklift.legacy.file_upload",
    uses_session=True,
    require_csrf=False,
    require_methods=["POST"],
)
def file_upload(request):
    # If we're in read-only mode, let upload clients know
    if request.flags.enabled('read-only'):
        raise _exc_with_message(
            HTTPForbidden,
            'Read Only Mode: Uploads are temporarily disabled',
        )

    # Before we do anything, if there isn't an authenticated user with this
    # request, then we'll go ahead and bomb out.
    if request.authenticated_userid is None:
        raise _exc_with_message(
            HTTPForbidden,
            "Invalid or non-existent authentication information.",
        )

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
            if '\x00' in value:
                request.POST[key] = value.replace('\x00', '\\x00')

    # We require protocol_version 1, it's the only supported version however
    # passing a different version should raise an error.
    if request.POST.get("protocol_version", "1") != "1":
        raise _exc_with_message(HTTPBadRequest, "Unknown protocol version.")

    # Check if any fields were supplied as a tuple and have become a
    # FieldStorage. The 'content' and 'gpg_signature' fields _should_ be a
    # FieldStorage, however.
    # ref: https://github.com/pypa/warehouse/issues/2185
    # ref: https://github.com/pypa/warehouse/issues/2491
    for field in set(request.POST) - {'content', 'gpg_signature'}:
        values = request.POST.getall(field)
        if any(isinstance(value, FieldStorage) for value in values):
            raise _exc_with_message(
                HTTPBadRequest,
                f"{field}: Should not be a tuple.",
            )

    # Look up all of the valid classifiers
    all_classifiers = request.db.query(Classifier).all()

    # Validate and process the incoming metadata.
    form = MetadataForm(request.POST)

    # Add a validator for deprecated classifiers
    form.classifiers.validators.append(_no_deprecated_classifiers(request))

    form.classifiers.choices = [
        (c.classifier, c.classifier) for c in all_classifiers
    ]
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
                        value=field.data,
                        field=field.description) +
                    "Error: {} ".format(form.errors[field_name][0]) +
                    "see "
                    "https://packaging.python.org/specifications/core-metadata"
                )
            else:
                error_message = (
                    "Invalid value for {field}. Error: {msgs[0]}".format(
                        field=field_name,
                        msgs=form.errors[field_name],
                    )
                )
        else:
            error_message = "Error: {}".format(form.errors[field_name][0])

        raise _exc_with_message(
            HTTPBadRequest,
            error_message,
        )

    # Ensure that we have file data in the request.
    if "content" not in request.POST:
        raise _exc_with_message(
            HTTPBadRequest,
            "Upload payload does not have a file.",
        )

    # Look up the project first before doing anything else, this is so we can
    # automatically register it if we need to and can check permissions before
    # going any further.
    try:
        project = (
            request.db.query(Project)
                      .filter(
                          Project.normalized_name ==
                          func.normalize_pep426_name(form.name.data)).one()
        )
    except NoResultFound:
        # Check for AdminFlag set by a PyPI Administrator disabling new project
        # registration, reasons for this include Spammers, security
        # vulnerabilities, or just wanting to be lazy and not worry ;)
        if request.flags.enabled('disallow-new-project-registration'):
            raise _exc_with_message(
                HTTPForbidden,
                ("New Project Registration Temporarily Disabled "
                 "See {projecthelp} for details")
                .format(
                    projecthelp=request.help_url(_anchor='admin-intervention'),
                ),
            ) from None

        # Ensure that user has at least one verified email address. This should
        # reduce the ease of spam account creation and activity.
        # TODO: Once legacy is shutdown consider the condition here, perhaps
        # move to user.is_active or some other boolean
        if not any(email.verified for email in request.user.emails):
            raise _exc_with_message(
                HTTPBadRequest,
                ("User {!r} has no verified email addresses, "
                 "please verify at least one address before registering "
                 "a new project on PyPI. See {projecthelp} "
                 "for more information.").format(
                    request.user.username,
                    projecthelp=request.help_url(_anchor='verified-email'),
                ),
            ) from None

        # Before we create the project, we're going to check our blacklist to
        # see if this project is even allowed to be registered. If it is not,
        # then we're going to deny the request to create this project.
        if request.db.query(exists().where(
                BlacklistedProject.name ==
                func.normalize_pep426_name(form.name.data))).scalar():
            raise _exc_with_message(
                HTTPBadRequest,
                ("The name {name!r} is not allowed. "
                 "See {projecthelp} "
                 "for more information.").format(
                    name=form.name.data,
                    projecthelp=request.help_url(_anchor='project-name'),
                ),
            ) from None

        # Also check for collisions with Python Standard Library modules.
        if (packaging.utils.canonicalize_name(form.name.data) in
                STDLIB_PROHIBITTED):
            raise _exc_with_message(
                HTTPBadRequest,
                ("The name {name!r} is not allowed (conflict with Python "
                 "Standard Library module name). See "
                 "{projecthelp} for more information.").format(
                    name=form.name.data,
                    projecthelp=request.help_url(_anchor='project-name')
                )
            ) from None

        # The project doesn't exist in our database, so we'll add it along with
        # a role setting the current user as the "Owner" of the project.
        project = Project(name=form.name.data)
        request.db.add(project)
        request.db.add(
            Role(user=request.user, project=project, role_name="Owner")
        )
        # TODO: This should be handled by some sort of database trigger or a
        #       SQLAlchemy hook or the like instead of doing it inline in this
        #       view.
        request.db.add(
            JournalEntry(
                name=project.name,
                action="create",
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            ),
        )
        request.db.add(
            JournalEntry(
                name=project.name,
                action="add Owner {}".format(request.user.username),
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            ),
        )

    # Check that the user has permission to do things to this project, if this
    # is a new project this will act as a sanity check for the role we just
    # added above.
    if not request.has_permission("upload", project):
        raise _exc_with_message(
            HTTPForbidden,
            ("The user '{0}' is not allowed to upload to project '{1}'. "
             "See {2} for more information.")
            .format(
                request.user.username,
                project.name,
                request.help_url(_anchor='project-name')
            )
        )

    try:
        canonical_version = packaging.utils.canonicalize_version(
            form.version.data
        )
        release = (
            request.db.query(Release)
            .filter(
                (Release.project == project) &
                (Release.canonical_version == canonical_version)
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
                (Release.project == project) &
                (Release.version == form.version.data)
            )
            .one()
        )
    except NoResultFound:
        release = Release(
            project=project,
            _classifiers=[
                c for c in all_classifiers
                if c.classifier in form.classifiers.data
            ],
            _pypi_hidden=False,
            dependencies=list(_construct_dependencies(
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
                }
            )),
            canonical_version=canonical_version,
            **{
                k: getattr(form, k).data
                for k in {
                    # This is a list of all the fields in the form that we
                    # should pull off and insert into our new release.
                    "version",
                    "summary", "description", "description_content_type",
                    "license",
                    "author", "author_email", "maintainer", "maintainer_email",
                    "keywords", "platform",
                    "home_page", "download_url",
                    "requires_python",
                }
            }
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
            ),
        )

    # TODO: We need a better solution to this than to just do it inline inside
    #       this method. Ideally the version field would just be sortable, but
    #       at least this should be some sort of hook or trigger.
    releases = (
        request.db.query(Release)
                  .filter(Release.project == project)
                  .options(orm.load_only(
                      Release._pypi_ordering,
                      Release._pypi_hidden))
                  .all()
    )
    for i, r in enumerate(sorted(
            releases, key=lambda x: packaging.version.parse(x.version))):
        r._pypi_ordering = i

    # TODO: Again, we should figure out a better solution to doing this than
    #       just inlining this inside this method.
    if project.autohide:
        for r in releases:
            r._pypi_hidden = bool(not r == release)

    # Pull the filename out of our POST data.
    filename = request.POST["content"].filename

    # Make sure that the filename does not contain any path separators.
    if "/" in filename or "\\" in filename:
        raise _exc_with_message(
            HTTPBadRequest,
            "Cannot upload a file with '/' or '\\' in the name.",
        )

    # Make sure the filename ends with an allowed extension.
    if _dist_file_regexes[project.allow_legacy_files].search(filename) is None:
        raise _exc_with_message(
            HTTPBadRequest,
            "Invalid file extension. PEP 527 requires one of: .egg, .tar.gz, "
            ".whl, .zip (https://www.python.org/dev/peps/pep-0527/)."
        )

    # Make sure that our filename matches the project that it is being uploaded
    # to.
    prefix = pkg_resources.safe_name(project.name).lower()
    if not pkg_resources.safe_name(filename).lower().startswith(prefix):
        raise _exc_with_message(
            HTTPBadRequest,
            "The filename for {!r} must start with {!r}.".format(
                project.name,
                prefix,
            )
        )

    # Check the content type of what is being uploaded
    if (not request.POST["content"].type or
            request.POST["content"].type.startswith("image/")):
        raise _exc_with_message(HTTPBadRequest, "Invalid distribution file.")

    # Ensure that the package filetype is allowed.
    # TODO: Once PEP 527 is completely implemented we should be able to delete
    #       this and just move it into the form itself.
    if (not project.allow_legacy_files and
            form.filetype.data not in {"sdist", "bdist_wheel", "bdist_egg"}):
        raise _exc_with_message(HTTPBadRequest, "Unknown type of file.")

    # The project may or may not have a file size specified on the project, if
    # it does then it may or may not be smaller or larger than our global file
    # size limits.
    file_size_limit = max(filter(None, [MAX_FILESIZE, project.upload_limit]))

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
            for chunk in iter(
                    lambda: request.POST["content"].file.read(8096), b""):
                file_size += len(chunk)
                if file_size > file_size_limit:
                    raise _exc_with_message(
                        HTTPBadRequest,
                        "File too large. " +
                        "Limit for project {name!r} is {limit}MB. ".format(
                            name=project.name,
                            limit=file_size_limit // (1024 * 1024)) +
                        "See " +
                        request.help_url(_anchor='file-size-limit'),
                    )
                fp.write(chunk)
                for hasher in file_hashes.values():
                    hasher.update(chunk)

        # Take our hash functions and compute the final hashes for them now.
        file_hashes = {
            k: h.hexdigest().lower()
            for k, h in file_hashes.items()
        }

        # Actually verify the digests that we've gotten. We're going to use
        # hmac.compare_digest even though we probably don't actually need to
        # because it's better safe than sorry. In the case of multiple digests
        # we expect them all to be given.
        if not all([
            hmac.compare_digest(
                getattr(form, "{}_digest".format(digest_name)).data.lower(),
                digest_value,
            )
            for digest_name, digest_value in file_hashes.items()
            if getattr(form, "{}_digest".format(digest_name)).data
        ]):
            raise _exc_with_message(
                HTTPBadRequest,
                "The digest supplied does not match a digest calculated "
                "from the uploaded file."
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
                "File already exists. See " +
                request.help_url(_anchor='file-name-reuse')
            )

        # Check to see if the file that was uploaded exists in our filename log
        if (request.db.query(
                request.db.query(Filename)
                          .filter(Filename.filename == filename)
                          .exists()).scalar()):
            raise _exc_with_message(
                HTTPBadRequest,
                "This filename has previously been used, you should use a "
                "different version. "
                "See " + request.help_url(_anchor='file-name-reuse'),
            )

        # Check to see if uploading this file would create a duplicate sdist
        # for the current release.
        if (form.filetype.data == "sdist" and
                request.db.query(
                    request.db.query(File)
                              .filter((File.release == release) &
                                      (File.packagetype == "sdist"))
                              .exists()).scalar()):
            raise _exc_with_message(
                HTTPBadRequest,
                "Only one sdist may be uploaded per release.",
            )

        # Check the file to make sure it is a valid distribution file.
        if not _is_valid_dist_file(temporary_filename, form.filetype.data):
            raise _exc_with_message(
                HTTPBadRequest,
                "Invalid distribution file.",
            )

        # Check that if it's a binary wheel, it's on a supported platform
        if filename.endswith(".whl"):
            wheel_info = _wheel_file_re.match(filename)
            plats = wheel_info.group("plat").split(".")
            for plat in plats:
                if not _valid_platform_tag(plat):
                    raise _exc_with_message(
                        HTTPBadRequest,
                        "Binary wheel '{filename}' has an unsupported "
                        "platform tag '{plat}'."
                        .format(filename=filename, plat=plat)
                    )

        # Also buffer the entire signature file to disk.
        if "gpg_signature" in request.POST:
            has_signature = True
            with open(os.path.join(tmpdir, filename + ".asc"), "wb") as fp:
                signature_size = 0
                for chunk in iter(
                        lambda: request.POST["gpg_signature"].file.read(8096),
                        b""):
                    signature_size += len(chunk)
                    if signature_size > MAX_SIGSIZE:
                        raise _exc_with_message(
                            HTTPBadRequest,
                            "Signature too large.",
                        )
                    fp.write(chunk)

            # Check whether signature is ASCII armored
            with open(os.path.join(tmpdir, filename + ".asc"), "rb") as fp:
                if not fp.read().startswith(b"-----BEGIN PGP SIGNATURE-----"):
                    raise _exc_with_message(
                        HTTPBadRequest,
                        "PGP signature is not ASCII armored.",
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
            path="/".join([
                file_hashes[PATH_HASHER][:2],
                file_hashes[PATH_HASHER][2:4],
                file_hashes[PATH_HASHER][4:],
                filename,
            ]),
        )
        request.db.add(file_)

        # TODO: This should be handled by some sort of database trigger or a
        #       SQLAlchemy hook or the like instead of doing it inline in this
        #       view.
        request.db.add(
            JournalEntry(
                name=release.project.name,
                version=release.version,
                action="add {python_version} file {filename}".format(
                    python_version=file_.python_version,
                    filename=file_.filename,
                ),
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            ),
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

    return Response()


def _legacy_purge(status, *args, **kwargs):
    if status:
        requests.post(*args, **kwargs)


@view_config(
    route_name="forklift.legacy.submit",
    require_csrf=False,
    require_methods=["POST"],
)
@view_config(
    route_name="forklift.legacy.submit_pkg_info",
    require_csrf=False,
    require_methods=["POST"],
)
def submit(request):
    return _exc_with_message(
        HTTPGone,
        ("Project pre-registration is no longer required or supported, so "
         "continue directly to uploading files."),
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
