# SPDX-License-Identifier: Apache-2.0
import hashlib
import hmac
import os.path
import re
import tarfile
import tempfile
import zipfile

from cgi import FieldStorage

import packaging.requirements
import packaging.specifiers
import packaging.utils
import packaging.version
import packaging_legacy.version
import sentry_sdk
import wtforms
import wtforms.validators

from pypi_attestations import Attestation, Distribution
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPException,
    HTTPForbidden,
    HTTPGone,
    HTTPOk,
    HTTPPermanentRedirect,
    HTTPTooManyRequests,
)
from pyramid.request import Request
from pyramid.view import view_config
from sqlalchemy import and_, exists, func, orm, text
from sqlalchemy.exc import MultipleResultsFound, NoResultFound

from warehouse.admin.flags import AdminFlagValue
from warehouse.attestations.errors import AttestationUploadError
from warehouse.attestations.interfaces import IIntegrityService
from warehouse.authnz import Permissions
from warehouse.classifiers.models import Classifier
from warehouse.constants import ONE_GIB, ONE_MIB
from warehouse.email import (
    send_api_token_used_in_trusted_publisher_project_email,
    send_wheel_record_mismatch_email,
)
from warehouse.events.tags import EventTag
from warehouse.forklift import metadata
from warehouse.forklift.forms import UploadForm, _filetype_extension_mapping
from warehouse.macaroons.models import Macaroon
from warehouse.packaging.interfaces import IFileStorage, IProjectService
from warehouse.packaging.metadata_verification import verify_email, verify_url
from warehouse.packaging.models import (
    Dependency,
    DependencyKind,
    Description,
    File,
    Filename,
    JournalEntry,
    Project,
    ProjectMacaroonWarningAssociation,
    Release,
)
from warehouse.packaging.tasks import sync_file_to_cache, update_bigquery_release_files
from warehouse.rate_limiting.interfaces import RateLimiterException
from warehouse.utils import readme, zipfiles
from warehouse.utils.release import strip_keywords
from warehouse.utils.wheel import (
    InvalidWheelRecordError,
    MissingWheelRecordError,
    validate_record,
)

PATH_HASHER = "blake2_256"

COMPRESSION_RATIO_MIN_SIZE = 64 * ONE_MIB

# If the zip file decompressed to 50x more space
# than it is uncompressed, consider it a ZIP bomb.
# Note that packages containing interface descriptions, JSON,
# such resources can compress really well.
# See discussion here: https://github.com/pypi/warehouse/issues/13962
COMPRESSION_RATIO_THRESHOLD = 50

# SQS has a maximum total message length of 262144 bytes. In order to stay
# under this when enqueuing a job to store BigQuery metadata, we truncate the
# Description field to 40K bytes, which captures up to the 95th percentile of
# existing descriptions.
MAX_DESCRIPTION_LENGTH_TO_BIGQUERY_IN_BYTES = 40000

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
_macosx_platform_re = re.compile(r"macosx_(?P<major>\d+)_(?P<minor>\d+)_(?P<arch>.*)")
_macosx_arches = {
    "ppc",
    "ppc64",
    "i386",
    "x86_64",
    "arm64",
    "intel",
    "fat",
    "fat3",
    "fat64",
    "universal",
    "universal2",
}
# macosx 10 is also supported, but with different rules
_macosx_major_versions = {
    "11",
    "12",
    "13",
    "14",
    "15",
    "26",
}

_ios_platform_re = re.compile(
    r"ios_(\d+)_(\d+)_(?P<arch>.*)_(iphoneos|iphonesimulator)"
)
_ios_arches = {
    "arm64",
    "x86_64",
}

_android_platform_re = re.compile(r"android_(\d+)_(?P<arch>.*)")
_android_arches = {
    "armeabi_v7a",
    "arm64_v8a",
    "x86",
    "x86_64",
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
    "riscv64",
}
_manylinux_arches = _jointlinux_arches | {"ppc64"}
_musllinux_arches = _jointlinux_arches


# Actual checking code;
def _valid_platform_tag(platform_tag):
    if platform_tag in _allowed_platforms:
        return True
    m = _macosx_platform_re.match(platform_tag)
    # https://github.com/pypa/packaging.python.org/issues/1933
    # There's two macosx formats: `macosx_10_{minor}` for the 10.x series where
    # only the minor version ever increased, and `macosx_{major}_0` for the
    # new release scheme where we don't know how many minor versions each
    # release has.
    if m and m.group("major") == "10" and m.group("arch") in _macosx_arches:
        return True
    if (
        m
        and m.group("major") in _macosx_major_versions
        and m.group("minor") == "0"
        and m.group("arch") in _macosx_arches
    ):
        return True
    m = _linux_platform_re.match(platform_tag)
    if m and m.group("libc") == "musl":
        return m.group("arch") in _musllinux_arches
    if m and m.group("libc") == "many":
        return m.group("arch") in _manylinux_arches
    m = _ios_platform_re.match(platform_tag)
    if m and m.group("arch") in _ios_arches:
        return True
    m = _android_platform_re.match(platform_tag)
    if m and m.group("arch") in _android_arches:
        return True
    return False


_error_message_order = ["metadata-version", "name", "version"]

_dist_file_re = re.compile(r".+?(?P<extension>\.(tar\.gz|zip|whl))$", re.I)


def _exc_with_message(exc, message, **kwargs):
    if not message:
        sentry_sdk.capture_message("Attempting to _exc_with_message without a message")

    # The crappy old API that PyPI offered uses the status to pass down
    # messages to the client. So this function will make that easier to do.
    resp = exc(detail=message, **kwargs)
    # We need to guard against characters outside of iso-8859-1 per RFC.
    # Specifically here, where user-supplied text may appear in the message,
    # which our WSGI server may not appropriately handle (indeed gunicorn does not).
    status_message = message.encode("iso-8859-1", "replace").decode("iso-8859-1")
    resp.status = f"{resp.status_code} {status_message}"
    return resp


def _construct_dependencies(meta: metadata.Metadata, types):
    for name, kind in types.items():
        for item in getattr(meta, name) or []:
            yield Dependency(kind=kind.value, specifier=str(item))


def _validate_filename(filename, filetype):
    # Our object storage does not tolerate some specific characters
    # ref: https://www.backblaze.com/b2/docs/files.html#file-names
    #
    # Also, its hard to imagine a usecase for them that isn't ✨malicious✨
    # or completely by mistake.
    disallowed = [*(chr(x) for x in range(32)), chr(127)]
    if [char for char in filename if char in disallowed]:
        raise _exc_with_message(
            HTTPBadRequest,
            (
                "Cannot upload a file with "
                "non-printable characters (ordinals 0-31) "
                "or the DEL character (ordinal 127) "
                "in the name."
            ),
        )

    # Make sure that the filename does not contain any path separators.
    if "/" in filename or "\\" in filename:
        raise _exc_with_message(
            HTTPBadRequest, "Cannot upload a file with '/' or '\\' in the name."
        )

    # Make sure the filename ends with an allowed extension.
    if m := _dist_file_re.match(filename):
        extension = m.group("extension")
        if extension not in _filetype_extension_mapping[filetype]:
            raise _exc_with_message(
                HTTPBadRequest,
                f"Invalid file extension: Extension {extension} is invalid for "
                f"filetype {filetype}. See https://www.python.org/dev/peps/pep-0527 "
                "for more information.",
            )
    else:
        raise _exc_with_message(
            HTTPBadRequest,
            "Invalid file extension: Use .tar.gz, .whl or .zip "
            "extension. See https://www.python.org/dev/peps/pep-0527 "
            "and https://peps.python.org/pep-0715/ for more information",
        )


def _is_valid_dist_file(filename, filetype):
    """
    Perform some basic checks to see whether the indicated file could be
    a valid distribution file.
    """

    if filename.endswith((".zip", ".whl")):
        if not zipfile.is_zipfile(filename):
            return False, "File is not a zipfile"
        # Ensure that this is a valid zip file, and that it has a
        # PKG-INFO or WHEEL file.
        try:
            with zipfile.ZipFile(filename) as zfp:
                # Ensure that the compression ratio is not absurd (decompression bomb)
                compressed_size = os.stat(filename).st_size
                decompressed_size = sum(e.file_size for e in zfp.infolist())
                if (
                    decompressed_size > COMPRESSION_RATIO_MIN_SIZE
                    and decompressed_size / compressed_size
                    > COMPRESSION_RATIO_THRESHOLD
                ):
                    sentry_sdk.capture_message(
                        f"File {filename} ({filetype}) exceeds compression ratio "
                        f"of {COMPRESSION_RATIO_THRESHOLD} "
                        f"({decompressed_size}/{compressed_size})"
                    )
                    return (
                        False,
                        "File exceeds compression ratio of "
                        f"{COMPRESSION_RATIO_THRESHOLD}",
                    )

                # Check that the compression type is valid
                for zinfo in zfp.infolist():
                    if zinfo.compress_type not in {
                        zipfile.ZIP_STORED,
                        zipfile.ZIP_DEFLATED,
                    }:
                        return (
                            False,
                            "File does not use a supported compression type",
                        )

                if filename.endswith(".zip"):
                    top_level = os.path.commonprefix(zfp.namelist())
                    if top_level in [".", "/", ""]:
                        return (
                            False,
                            "Incorrect number of top-level directories in sdist",
                        )
                    target_file = os.path.join(top_level, "PKG-INFO")
                    try:
                        zfp.read(target_file)
                    except KeyError:
                        return False, f"PKG-INFO not found at {target_file}"
                if filename.endswith(".whl"):
                    try:
                        name, version, _ = os.path.basename(filename).split("-", 2)
                    except ValueError:
                        return (
                            False,
                            "Unable to parse name and version from wheel filename",
                        )
                    target_file = os.path.join(f"{name}-{version}.dist-info", "WHEEL")
                    try:
                        zfp.read(target_file)
                    except KeyError:
                        return False, f"WHEEL not found at {target_file}"

            # Check the ZIP file record framing
            # to avoid parser differentials.
            zip_ok, zip_error = zipfiles.validate_zipfile(filename)
            if not zip_ok:
                return False, (
                    f"ZIP archive not accepted: {zip_error}. "
                    f"See https://docs.pypi.org/archives for more information"
                )

        except zipfile.BadZipFile:  # pragma: no cover
            return False, None

    elif filename.endswith(".tar.gz"):
        if not tarfile.is_tarfile(filename):
            return False, "File is not a tarfile"
        # Ensure that this is a valid tar file, and that it contains PKG-INFO.
        # TODO: Ideally Ensure the compression ratio is not absurd
        # (decompression bomb), like we do for wheel/zip above.
        try:
            with tarfile.open(filename, "r:gz") as tar:
                # This decompresses the entire stream to validate it and the
                # tar within.  Easy CPU DoS attack. :/
                top_level = os.path.commonprefix(tar.getnames())
                if top_level in [".", "/", ""]:
                    return (
                        False,
                        "Incorrect number of top-level directories in sdist",
                    )
                target_file = os.path.join(top_level, "PKG-INFO")
                try:
                    tar.getmember(target_file)
                except KeyError:
                    return False, f"PKG-INFO not found at {target_file}"
        except (tarfile.ReadError, EOFError):
            return False, None

    # If we haven't yet decided it's not valid, then we'll assume it is and
    # allow it.
    return True, None


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
            and file_.blake2_256_digest == hashes["blake2_256"]
        )

    return None


def _sort_releases(request: Request, project: Project):
    releases = (
        request.db.query(Release)
        .filter(Release.project == project)
        .options(
            orm.load_only(
                Release.project_id,
                Release.version,
                Release._pypi_ordering,
            )
        )
        .all()
    )
    for i, r in enumerate(
        sorted(releases, key=lambda x: packaging_legacy.version.parse(x.version))
    ):
        # NOTE: If we set r._pypi_ordering, even to the same value it was
        #       previously, then SQLAlchemy will decide that it needs to load
        #       Release.description (with N+1 queries) for some reason that I
        #       can't possibly fathom why. The SQLAlchemy docs say that
        #       raisedload doesn't prevent SQLAlchemy for doing queries that it
        #       needs to do for the Unit of Work pattern, so I guess since each
        #       Release object was modified it feels the need to load each of
        #       them... but I haven no idea why that means it feels the need to
        #       load the Release.description relationship as well.
        #
        #       Technically, we can still execute a query for every release if
        #       someone goes back and releases a version "0" or something that
        #       would cause most or all of the releases to need to "shift" and
        #       get updated.
        #
        #       We maybe want to convert this away from using the ORM and build up
        #       a mapping of Release.id -> new _pypi_ordering and do a single bulk
        #       update query to eliminate the possibility we trigger this again.
        if r._pypi_ordering != i:
            r._pypi_ordering = i


@view_config(
    route_name="forklift.legacy.file_upload",
    uses_session=True,
    require_csrf=False,
    require_methods=["POST"],
    has_translations=True,
    permit_duplicate_post_keys=True,
)
def file_upload(request):
    # Log an attempt to upload
    request.metrics.increment("warehouse.upload.attempt")

    # This is a list of warnings that we'll emit *IF* the request is successful.
    warnings: list[str] = []

    # If we're in read-only mode, let upload clients know
    if request.flags.enabled(AdminFlagValue.READ_ONLY):
        request.metrics.increment("warehouse.upload.failed", tags=["reason:read-only"])
        raise _exc_with_message(
            HTTPForbidden, "Read-only mode: Uploads are temporarily disabled."
        )

    if request.flags.enabled(AdminFlagValue.DISALLOW_NEW_UPLOAD):
        request.metrics.increment(
            "warehouse.upload.failed", tags=["reason:uploads-disabled"]
        )
        raise _exc_with_message(
            HTTPForbidden,
            "New uploads are temporarily disabled. "
            "See {projecthelp} for more information.".format(
                projecthelp=request.help_url(_anchor="admin-intervention")
            ),
        )

    # Before we do anything, if there isn't an authenticated identity with
    # this request, then we'll go ahead and bomb out.
    if request.identity is None:
        request.metrics.increment(
            "warehouse.upload.failed", tags=["reason:no-identity"]
        )
        raise _exc_with_message(
            HTTPForbidden,
            "Invalid or non-existent authentication information. "
            "See {projecthelp} for more information.".format(
                projecthelp=request.help_url(_anchor="invalid-auth")
            ),
        )

    # These checks only make sense when our authenticated identity is a user,
    # not a project identity (like OIDC-minted tokens.)
    if request.user:
        # Ensure that user has a verified, primary email address. This should both
        # reduce the ease of spam account creation and activity, as well as act as
        # a forcing function for https://github.com/pypa/warehouse/issues/3632.
        # TODO: Once https://github.com/pypa/warehouse/issues/3632 has been solved,
        #       we might consider a different condition, possibly looking at
        #       User.is_active instead.
        if not (request.user.primary_email and request.user.primary_email.verified):
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:unverified-email"]
            )
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
        # Ensure user has enabled 2FA before they can upload a file.
        if not request.user.has_two_factor:
            request.metrics.increment("warehouse.upload.failed", tags=["reason:no-2fa"])
            raise _exc_with_message(
                HTTPBadRequest,
                (
                    "User {!r} does not have two-factor authentication enabled. "
                    "Please enable two-factor authentication before attempting to "
                    "upload to PyPI. See {project_help} for more information."
                ).format(
                    request.user.username,
                    project_help=request.help_url(_anchor="two-factor-authentication"),
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
        request.metrics.increment(
            "warehouse.upload.failed", tags=["reason:unsupported-protocol-version"]
        )
        raise _exc_with_message(HTTPBadRequest, "Unknown protocol version.")

    # Check if any fields were supplied as a tuple and have become a
    # FieldStorage. The 'content' field _should_ be a FieldStorage, however,
    # and we don't care about the legacy gpg_signature field.
    # ref: https://github.com/pypi/warehouse/issues/2185
    # ref: https://github.com/pypi/warehouse/issues/2491
    for field in set(request.POST) - {"content", "gpg_signature"}:
        values = request.POST.getall(field)
        if any(isinstance(value, FieldStorage) for value in values):
            request.metrics.increment(
                "warehouse.upload.failed",
                tags=["reason:field-is-tuple", f"field:{field}"],
            )
            raise _exc_with_message(HTTPBadRequest, f"{field}: Should not be a tuple.")

    # Validate and process the incoming file data.
    form = UploadForm(request.POST)

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

        request.metrics.increment(
            "warehouse.upload.failed", tags=["reason:invalid-form-data"]
        )
        raise _exc_with_message(HTTPBadRequest, error_message)

    # Get a validated Metadata object from the form data.
    # TODO: We should eventually extract this data out of the artifact and use that,
    #       but for now we'll continue to use the form data.
    try:
        meta = metadata.parse(None, form_data=request.POST)
    except* metadata.InvalidMetadata as exc:
        # Turn our list of errors into a mapping of errors, keyed by the field
        errors: dict = {}
        for error in exc.exceptions:
            errors.setdefault(error.field, []).append(error)

        # These errors are most important, because they tend to influence all of
        # the other errors.
        for field_name in _error_message_order:
            if field_name in errors:
                break
        else:
            field_name = sorted(errors.keys())[0]

        # Return an error for the field, using the first error that we can find
        # for that field
        error = errors[field_name][0]
        error_msg = str(error)
        request.metrics.increment(
            "warehouse.upload.failed", tags=["reason:invalid-metadata"]
        )
        raise _exc_with_message(
            HTTPBadRequest,
            " ".join(
                [
                    error_msg + ("." if not error_msg.endswith(".") else ""),
                    "See https://packaging.python.org/specifications/core-metadata "
                    "for more information.",
                ]
            ),
        )

    # Ensure that we have file data in the request.
    if "content" not in request.POST:
        request.metrics.increment("warehouse.upload.failed", tags=["reason:no-file"])
        raise _exc_with_message(HTTPBadRequest, "Upload payload does not have a file.")

    # Set a statement timeout for this connection to prevent long-running
    # transactions from holding database locks indefinitely. The upload
    # operation holds a global advisory lock for journal monotonicity,
    # so limiting transaction duration prevents lock pile-up.
    # 600 seconds (10 minutes) allows for large file uploads while
    # providing an upper bound on lock duration.
    request.db.execute(text("SET statement_timeout = '600s'"))

    # Look up the project first before doing anything else, this is so we can
    # automatically register it if we need to and can check permissions before
    # going any further.
    project = (
        request.db.query(Project)
        .filter(Project.normalized_name == func.normalize_pep426_name(form.name.data))
        .first()
    )

    if project is None:
        # Another sanity check: we should be preventing non-user identities
        # from creating projects in the first place with scoped tokens,
        # but double-check anyways.
        # This can happen if a user mismatches between the project name in
        # their pending publisher (1) and the project name in their metadata (2):
        # the pending publisher will create an empty project named (1) and will
        # produce a valid API token, but the project lookup above uses (2)
        # and will fail because (1) != (2).
        if not request.user:
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:non-user-identity"]
            )
            raise _exc_with_message(
                HTTPBadRequest,
                (
                    "Non-user identities cannot create new projects. "
                    "This was probably caused by successfully using a pending "
                    "publisher but specifying the project name incorrectly (either "
                    "in the publisher or in your project's metadata). Please ensure "
                    "that both match. "
                    "See: https://docs.pypi.org/trusted-publishers/troubleshooting/"
                ),
            )

        # We attempt to create the project.
        project_service = request.find_service(IProjectService)
        try:
            project = project_service.create_project(
                form.name.data, request.user, request
            )
        except HTTPException as exc:
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:project-creation-failed"]
            )
            raise _exc_with_message(exc.__class__, exc.detail) from None
        except RateLimiterException:
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:rate-limited"]
            )
            msg = "Too many new projects created"
            raise _exc_with_message(HTTPTooManyRequests, msg)

    # Check that the identity has permission to do things to this project, if this
    # is a new project this will act as a sanity check for the role we just
    # added above.
    allowed = request.has_permission(Permissions.ProjectsUpload, project)
    if not allowed:
        reason = getattr(allowed, "reason", None)
        if request.user:
            msg = (
                (
                    "The user '{}' isn't allowed to upload to project '{}'. "
                    "See {} for more information."
                ).format(
                    request.user.username,
                    project.name,
                    request.help_url(_anchor="project-name"),
                )
                if reason is None
                else allowed.msg
            )
        else:
            msg = (
                (
                    "The given token isn't allowed to upload to project '{}'. "
                    "See {} for more information."
                ).format(
                    project.name,
                    request.help_url(_anchor="project-name"),
                )
                if reason is None
                else allowed.msg
            )
        request.metrics.increment(
            "warehouse.upload.failed", tags=["reason:permission-denied"]
        )
        raise _exc_with_message(HTTPForbidden, msg)

    # If organization owned project, check if the organization is active.
    # Inactive organizations cannot upload new releases to their projects.
    if project.organization and not project.organization.good_standing:
        request.metrics.increment(
            "warehouse.upload.failed", tags=["reason:org-not-active"]
        )
        raise _exc_with_message(
            HTTPBadRequest,
            (
                "Organization account owning this project is inactive. "
                "This may be due to inactive billing for Company Organizations, "
                "or administrator intervention for Community Organizations. "
                "Please contact support+orgs@pypi.org."
            ),
        )

    # If this is a user identity (i.e: API token) but there exists
    # a trusted publisher for this project, send an email warning that an
    # API token was used to upload a project where Trusted Publishing is configured.
    # Only do this once per (API token, project) combination.
    if request.user and project.oidc_publishers:
        macaroon: Macaroon = request.identity.macaroon
        # If we haven't warned about use of this particular API token and project
        # combination, send the warning email
        warning_exists = request.db.query(
            exists().where(
                and_(
                    ProjectMacaroonWarningAssociation.macaroon_id == macaroon.id,
                    ProjectMacaroonWarningAssociation.project_id == project.id,
                )
            )
        ).scalar()
        if not warning_exists:
            send_api_token_used_in_trusted_publisher_project_email(
                request,
                set(project.users),
                project_name=project.name,
                token_owner_username=request.user.username,
                token_name=macaroon.description,
            )
            request.db.add(
                ProjectMacaroonWarningAssociation(
                    macaroon_id=macaroon.id,
                    project_id=project.id,
                )
            )
    # Update name if it differs but is still equivalent. We don't need to check if
    # they are equivalent when normalized because that's already been done when we
    # queried for the project.
    if project.name != meta.name:
        project.name = meta.name

    # Render our description so we can save from having to render this data every time
    # we load a project description page.
    rendered = None
    if meta.description:
        description_content_type = meta.description_content_type or "text/x-rst"

        rendered = readme.render(
            meta.description, description_content_type, use_fallback=False
        )

        # Uploading should prevent broken rendered descriptions.
        if rendered is None:
            if meta.description_content_type:
                message = (
                    "The description failed to render for '{description_content_type}'."
                ).format(description_content_type=description_content_type)
            else:
                message = (
                    "The description failed to render "
                    "in the default format of reStructuredText."
                )
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:invalid-description"]
            )
            raise _exc_with_message(
                HTTPBadRequest,
                "{message} See {projecthelp} for more information.".format(
                    message=message,
                    projecthelp=request.help_url(_anchor="description-content-type"),
                ),
            ) from None

    # Verify any verifiable URLs
    project_urls = (
        {}
        if not meta.project_urls
        else {
            name: {
                "url": url,
                "verified": verify_url(
                    url=url,
                    publisher=request.oidc_publisher,
                    project_name=project.name,
                    project_normalized_name=project.normalized_name,
                ),
            }
            for name, url in meta.project_urls.items()
        }
    )
    home_page = meta.home_page
    home_page_verified = (
        False
        if home_page is None
        else verify_url(
            url=home_page,
            publisher=request.oidc_publisher,
            project_name=project.name,
            project_normalized_name=project.normalized_name,
        )
    )

    download_url = meta.download_url
    download_url_verified = (
        False
        if download_url is None
        else verify_url(
            url=download_url,
            publisher=request.oidc_publisher,
            project_name=project.name,
            project_normalized_name=project.normalized_name,
        )
    )

    author_email = meta.author_email
    author_email_verified = (
        False
        if author_email is None
        else verify_email(email=author_email, project=project)
    )
    maintainer_email = meta.maintainer_email
    maintainer_email_verified = (
        False
        if maintainer_email is None
        else verify_email(email=maintainer_email, project=project)
    )

    try:
        is_new_release = False
        canonical_version = packaging.utils.canonicalize_version(meta.version)
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
                (Release.project == project) & (Release.version == str(meta.version))
            )
            .one()
        )
    except NoResultFound:
        # Get all the classifiers for this release
        release_classifiers = (
            request.db.query(Classifier)
            .filter(Classifier.classifier.in_(meta.classifiers or []))
            .all()
        )

        release = Release(
            project=project,
            _classifiers=release_classifiers,
            dependencies=list(
                _construct_dependencies(
                    meta,
                    {
                        "requires": DependencyKind.requires,
                        "provides": DependencyKind.provides,
                        "obsoletes": DependencyKind.obsoletes,
                        "requires_dist": DependencyKind.requires_dist,
                        "provides_dist": DependencyKind.provides_dist,
                        "obsoletes_dist": DependencyKind.obsoletes_dist,
                        "requires_external": DependencyKind.requires_external,
                    },
                )
            ),
            version=str(meta.version),
            canonical_version=canonical_version,
            description=Description(
                content_type=meta.description_content_type,
                raw=meta.description or "",
                html=rendered or "",
                rendered_by=readme.renderer_version(),
            ),
            home_page=home_page,
            home_page_verified=home_page_verified,
            download_url=download_url,
            download_url_verified=download_url_verified,
            project_urls=project_urls,
            author_email=author_email,
            author_email_verified=author_email_verified,
            maintainer_email=maintainer_email,
            maintainer_email_verified=maintainer_email_verified,
            # TODO: Fix this, we currently treat platform as if it is a single
            #       use field, but in reality it is a multi-use field, which the
            #       packaging.metadata library handles correctly.
            #
            #       For now, we'll simulate the old behavior by picking the first
            #       value, if there is a value.
            platform=meta.platforms[0] if meta.platforms else None,
            # TODO: packaging.metadata has already parsed this into a list for us,
            #       which we now go and turn it back into a string, we should fix
            #       this and store this as a list.
            keywords=", ".join(meta.keywords) if meta.keywords else None,
            keywords_array=(strip_keywords(meta.keywords) if meta.keywords else None),
            requires_python=str(meta.requires_python) if meta.requires_python else None,
            # Since dynamic field values are RFC 822 email headers, which are
            # case-insensitive, normalize them to title-case so we don't have
            # to store every possible variation, and can use an enum to restrict them
            # in the database
            dynamic=[x.title() for x in meta.dynamic] if meta.dynamic else None,
            **{
                k: getattr(meta, k)
                for k in {
                    # This is a list of all the fields in the form that we
                    # should pull off and insert into our new release.
                    "summary",
                    "license",
                    "license_expression",
                    "license_files",
                    "author",
                    "maintainer",
                    "provides_extra",
                }
            },
            uploader=request.user if request.user else None,
            uploaded_via=request.user_agent,
        )
        request.db.add(release)
        is_new_release = True

        # TODO: This should be handled by some sort of database trigger or
        #       a SQLAlchemy hook or the like instead of doing it inline in
        #       this view.
        request.db.add(
            JournalEntry(
                name=release.project.name,
                version=release.version,
                action="new release",
                submitted_by=request.user if request.user else None,
            )
        )

        project.record_event(
            tag=EventTag.Project.ReleaseAdd,
            request=request,
            additional={
                "submitted_by": (
                    request.user.username if request.user else "OpenID created token"
                ),
                "canonical_version": release.canonical_version,
                "publisher_url": (
                    request.oidc_publisher.publisher_url(request.oidc_claims)
                    if request.oidc_publisher
                    else None
                ),
                "uploaded_via_trusted_publisher": bool(request.oidc_publisher),
            },
        )

        # TODO: We need a better solution to this than to just do it inline inside
        #       this method. Ideally the version field would just be sortable, but
        #       at least this should be some sort of hook or trigger.
        _sort_releases(request, project)

    # Pull the filename out of our POST data.
    filename = request.POST["content"].filename

    # Ensure the filename doesn't contain any characters that are too 🌶️spicy🥵
    # TODO: refactor to accept `request` and emit metrics, or return a list of errors
    #  and handle them here and emit metrics.
    _validate_filename(filename, filetype=form.filetype.data)

    # Check the content type of what is being uploaded
    if not request.POST["content"].type or request.POST["content"].type.startswith(
        "image/"
    ):
        request.metrics.increment(
            "warehouse.upload.failed", tags=["reason:invalid-content-type"]
        )
        raise _exc_with_message(HTTPBadRequest, "Invalid distribution file.")

    # The project may or may not have a file size specified on the project, if
    # it does then it may or may not be smaller or larger than our global file
    # size limits. Additionally, if the project belongs to an organization,
    # we also consider the organization's limits and use the most generous one.
    file_size_limit = project.upload_limit_size
    project_size_limit = project.total_size_limit_value

    file_data = None
    with tempfile.TemporaryDirectory() as tmpdir:
        temporary_filename = os.path.join(tmpdir, filename)

        # Buffer the entire file onto disk, checking the hash of the file as we
        # go along.
        with open(temporary_filename, "wb") as fp:
            file_size = 0
            file_hashes = {
                "md5": hashlib.md5(usedforsecurity=False),
                "sha256": hashlib.sha256(),
                "blake2_256": hashlib.blake2b(digest_size=256 // 8),
            }
            metadata_file_hashes = {}
            for chunk in iter(lambda: request.POST["content"].file.read(8096), b""):
                file_size += len(chunk)
                if file_size > file_size_limit:
                    raise _exc_with_message(
                        HTTPBadRequest,
                        "File too large. "
                        + "Limit for project {name!r} is {limit} MB. ".format(
                            name=project.name, limit=file_size_limit // ONE_MIB
                        )
                        + "See "
                        + request.user_docs_url(
                            "/project-management/storage-limits",
                            anchor="requesting-a-file-size-limit-increase",
                        )
                        + " for more information.",
                    )
                if file_size + project.total_size > project_size_limit:
                    raise _exc_with_message(
                        HTTPBadRequest,
                        "Project size too large. Limit for "
                        + "project {name!r} total size is {limit} GB. ".format(
                            name=project.name, limit=project_size_limit // ONE_GIB
                        )
                        + "See "
                        + request.user_docs_url(
                            "/project-management/storage-limits",
                            anchor="requesting-a-project-size-limit-increase",
                        ),
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
                    getattr(form, f"{digest_name}_digest").data.lower(),
                    digest_value,
                )
                for digest_name, digest_value in file_hashes.items()
                if getattr(form, f"{digest_name}_digest").data
            ]
        ):
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:digest-mismatch"]
            )
            raise _exc_with_message(
                HTTPBadRequest,
                "The digest supplied does not match a digest calculated "
                "from the uploaded file.",
            )

        # Check to see if the file that was uploaded exists already or not.
        is_duplicate = _is_duplicate_file(request.db, filename, file_hashes)
        if is_duplicate:
            request.tm.doom()
            return HTTPOk()
        elif is_duplicate is not None:
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:duplicate-file"]
            )
            raise _exc_with_message(
                HTTPBadRequest,
                # Note: Changing this error message to something that doesn't
                # start with "File already exists" will break the
                # --skip-existing functionality in twine
                # ref: https://github.com/pypi/warehouse/issues/3482
                # ref: https://github.com/pypa/twine/issues/332
                "File already exists "
                + f"({filename!r}, with blake2_256 hash {file_hashes['blake2_256']!r})."
                + " See "
                + request.help_url(_anchor="file-name-reuse")
                + " for more information.",
            )

        # Check to see if the file that was uploaded exists in our filename log
        if request.db.query(
            request.db.query(Filename).filter(Filename.filename == filename).exists()
        ).scalar():
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:filename-reuse"]
            )
            raise _exc_with_message(
                HTTPBadRequest,
                "This filename was previously used by a file that has since been "
                "deleted. Use a different version. See "
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
            request.metrics.increment(
                "warehouse.upload.failed", tags=["reason:duplicate-sdist"]
            )
            raise _exc_with_message(
                HTTPBadRequest, "Only one sdist may be uploaded per release."
            )

        # Check the file to make sure it is a valid distribution file.
        _valid, _msg = _is_valid_dist_file(
            temporary_filename,
            form.filetype.data,
        )
        if not _valid:
            request.metrics.increment(
                "warehouse.upload.failed",
                tags=[
                    "reason:invalid-distribution-file",
                    f"filetype:{form.filetype.data}",
                ],
            )
            raise _exc_with_message(
                HTTPBadRequest, f"Invalid distribution file. {_msg}"
            )

        # Check that the sdist filename is correct
        if form.filetype.data == "sdist":

            # Extract the project name and version from the filename and check it.
            try:
                name_from_filename, version_from_filename = (
                    packaging.utils.parse_sdist_filename(filename)
                )
            except packaging.utils.InvalidSdistFilename:
                request.metrics.increment(
                    "warehouse.upload.failed",
                    tags=["reason:invalid-filename", f"filetype:{form.filetype.data}"],
                )
                raise _exc_with_message(
                    HTTPBadRequest,
                    f"Invalid source distribution filename: {filename}",
                )

            # The previous function fails to accomodate the edge case where
            # versions may contain hyphens, so we handle that here based on
            # what we were expecting. This requires there to be at least two
            # hyphens in the filename: one between the project name & version
            # and one inside the version
            if (
                meta.version.is_postrelease
                and name_from_filename != packaging.utils.canonicalize_name(meta.name)
                and filename.count("-") >= 2
            ):
                try:
                    # The distribution is a source distribution, the version is a
                    # postrelease, and the project name doesn't match, so
                    # there may be a hyphen in the version. Split the filename on the
                    # second to last hyphen instead.
                    name_from_filename = filename.rpartition("-")[0].rpartition("-")[0]
                    version_string_from_filename = filename[
                        len(name_from_filename) + 1 : -len(".tar.gz")
                    ]
                    packaging.version.Version(version_string_from_filename)
                except packaging.version.InvalidVersion:
                    # If the version isn't valid, we're not on this edge case.
                    pass

            # Check if the file corresponds to the project by comparing the
            # canonicalized name in the filename to the project name. This does
            # not enforce normalization.
            if (
                packaging.utils.canonicalize_name(name_from_filename)
                != project.normalized_name
            ):
                request.metrics.increment(
                    "warehouse.upload.failed",
                    tags=[
                        "reason:invalid-filename-normalized",
                        f"filetype:{form.filetype.data}",
                    ],
                )
                raise _exc_with_message(
                    HTTPBadRequest,
                    f"Start filename for {project.name!r} with "
                    f"{project.normalized_name.replace('-', '_')!r}.",
                )

            # PEP 625: Enforcement of source distribution filename
            # normalization.
            expected_name = project.normalized_name.replace("-", "_")
            expected_version = str(meta.version)
            expected_filename = f"{expected_name}-{expected_version}.tar.gz"

            if filename != expected_filename:
                request.metrics.increment(
                    "warehouse.upload.failed",
                    tags=["reason:invalid-sdist-filename-normalization"],
                )
                raise _exc_with_message(
                    HTTPBadRequest,
                    f"Filename {filename!r} is invalid, should be "
                    f"{expected_filename!r}.",
                )

            filename = os.path.basename(temporary_filename)

            if meta.license_files:
                """
                Ensure all License-File keys exist in the sdist
                See https://peps.python.org/pep-0639/#add-license-file-field
                """
                with tarfile.open(temporary_filename, "r:gz") as tar:
                    top_level = os.path.commonprefix(tar.getnames())
                    # Already validated as a tarfile by _is_valid_dist_file above
                    for license_file in meta.license_files:
                        target_file = os.path.join(top_level, license_file)
                        try:
                            tar.getmember(target_file)
                        except KeyError:
                            request.metrics.increment(
                                "warehouse.upload.failed",
                                tags=[
                                    "reason:missing-license-file",
                                    f"filetype:{form.filetype.data}",
                                ],
                            )
                            raise _exc_with_message(
                                HTTPBadRequest,
                                f"License-File {license_file} does not exist in "
                                f"distribution file {filename} at {target_file}",
                            )

        # Check that if it's a binary wheel, it's on a supported platform
        if filename.endswith(".whl"):
            try:
                name, version, ___, tags = packaging.utils.parse_wheel_filename(
                    filename
                )
            except packaging.utils.InvalidWheelFilename as e:
                request.metrics.increment(
                    "warehouse.upload.failed",
                    tags=["reason:invalid-filename", f"filetype:{form.filetype.data}"],
                )
                raise _exc_with_message(
                    HTTPBadRequest,
                    str(e),
                )

            for tag in tags:
                if not _valid_platform_tag(tag.platform):
                    request.metrics.increment(
                        "warehouse.upload.failed",
                        tags=["reason:unsupported-platform-tag"],
                    )
                    raise _exc_with_message(
                        HTTPBadRequest,
                        f"Binary wheel '{filename}' has an unsupported "
                        f"platform tag '{tag.platform}'.",
                    )

            if (canonical_name := packaging.utils.canonicalize_name(meta.name)) != name:
                request.metrics.increment(
                    "warehouse.upload.failed",
                    tags=[
                        "reason:invalid-filename-normalized",
                        f"filetype:{form.filetype.data}",
                    ],
                )
                raise _exc_with_message(
                    HTTPBadRequest,
                    f"Start filename for {project.name!r} with "
                    f"{canonical_name.replace('-', '_')!r}.",
                )

            # The parse_wheel_filename function does not enforce lowercasing,
            # and also returns a normalized name, so we must get the original
            # distribution name from the filename manually
            name_from_filename, _ = filename.split("-", 1)

            # PEP 427 / PEP 503: Enforcement of project name normalization.
            # Filenames that do not start with the fully normalized project name
            # are not be permitted.
            # https://packaging.python.org/en/latest/specifications/binary-distribution-format/#escaping-and-unicode
            normalized_name = project.normalized_name.replace("-", "_")
            if name_from_filename != normalized_name:
                request.metrics.increment(
                    "warehouse.upload.failed",
                    tags=[
                        "reason:invalid-filename-projectname",
                        f"filetype:{form.filetype.data}",
                    ],
                )
                raise _exc_with_message(
                    HTTPBadRequest,
                    f"Filename {filename!r} should contain the normalized "
                    f"project name {normalized_name!r}, not "
                    f"{name_from_filename!r}.",
                )

            if meta.version != version:
                request.metrics.increment(
                    "warehouse.upload.failed",
                    tags=[
                        "reason:invalid-filename-version",
                        f"filetype:{form.filetype.data}",
                    ],
                )
                raise _exc_with_message(
                    HTTPBadRequest,
                    f"Version in filename should be {str(meta.version)!r} not "
                    f"{str(version)!r}.",
                )

            filename = os.path.basename(temporary_filename)
            # Get the name and version from the original filename. Eventually this
            # should use packaging.utils.parse_wheel_filename(filename), but until then
            # we can't use this as it adds additional normailzation to the project name
            # and version.
            name, version, _ = filename.split("-", 2)

            if meta.license_files:
                """
                Ensure all License-File keys exist in the wheel
                See https://peps.python.org/pep-0639/#add-license-file-field
                """
                with zipfile.ZipFile(temporary_filename) as zfp:
                    for license_file in meta.license_files:
                        license_filename = (
                            f"{name}-{version}.dist-info/licenses/{license_file}"
                        )
                        try:
                            zfp.read(license_filename)
                        except KeyError:
                            request.metrics.increment(
                                "warehouse.upload.failed",
                                tags=[
                                    "reason:missing-license-file",
                                    f"filetype:{form.filetype.data}",
                                ],
                            )
                            raise _exc_with_message(
                                HTTPBadRequest,
                                f"License-File {license_file} does not exist in "
                                f"distribution file {filename} at {license_filename}",
                            )

            try:
                validate_record(temporary_filename)
            except MissingWheelRecordError:
                request.metrics.increment(
                    "warehouse.upload.failed",
                    tags=[
                        "reason:missing-record-file",
                        f"filetype:{form.filetype.data}",
                    ],
                )
                raise _exc_with_message(
                    HTTPBadRequest,
                    "Wheel '{filename}' does not contain the required "
                    "RECORD file: {record_filename}".format(
                        filename=filename,
                        record_filename=f"{name}-{version}.dist-info/RECORD",
                    ),
                )
            except InvalidWheelRecordError:
                send_wheel_record_mismatch_email(
                    request,
                    set(project.users),
                    project_name=project.name,
                    filename=filename,
                )

            """
            Extract METADATA file from a wheel and return it as a content.
            The name of the .whl file is used to find the corresponding .dist-info dir.
            See https://peps.python.org/pep-0491/#file-contents
            """
            metadata_filename = f"{name}-{version}.dist-info/METADATA"
            try:
                with zipfile.ZipFile(temporary_filename) as zfp:
                    wheel_metadata_contents = zfp.read(metadata_filename)
            except KeyError:
                request.metrics.increment(
                    "warehouse.upload.failed",
                    tags=[
                        "reason:missing-metadata-file",
                        f"filetype:{form.filetype.data}",
                    ],
                )
                raise _exc_with_message(
                    HTTPBadRequest,
                    "Wheel '{filename}' does not contain the required "
                    "METADATA file: {metadata_filename}".format(
                        filename=filename, metadata_filename=metadata_filename
                    ),
                )
            try:
                with open(temporary_filename + ".metadata", "wb") as fp:
                    fp.write(wheel_metadata_contents)
            except OSError:
                request.metrics.increment(
                    "warehouse.upload.failed",
                    tags=[
                        "reason:filename-too-long",
                        f"filetype:{form.filetype.data}",
                    ],
                )
                raise _exc_with_message(
                    HTTPBadRequest,
                    f"Filename is too long: '{filename}'",
                )

            metadata_file_hashes = {
                "sha256": hashlib.sha256(),
                "blake2_256": hashlib.blake2b(digest_size=256 // 8),
            }
            for hasher in metadata_file_hashes.values():
                hasher.update(wheel_metadata_contents)
            metadata_file_hashes = {
                k: h.hexdigest().lower() for k, h in metadata_file_hashes.items()
            }

        # If the user provided attestations, verify them
        # We persist these attestations subsequently, only after the
        # release file is persisted.
        integrity_service: IIntegrityService = request.find_service(
            IIntegrityService, context=None
        )
        attestations: list[Attestation] = []
        if "attestations" in request.POST and not request.flags.enabled(
            AdminFlagValue.DISABLE_PEP740
        ):
            try:
                attestations = integrity_service.parse_attestations(
                    request,
                    Distribution(name=filename, digest=file_hashes["sha256"]),
                )
            except AttestationUploadError as e:
                request.metrics.increment(
                    "warehouse.upload.failed", tags=["reason:invalid-attestations"]
                )
                raise _exc_with_message(
                    HTTPBadRequest,
                    f"Invalid attestations supplied during upload: {e}",
                )

        # Store the information about the file in the database.
        file_ = File(
            release=release,
            filename=filename,
            python_version=form.pyversion.data,
            packagetype=form.filetype.data,
            comment_text=form.comment.data,
            size=file_size,
            md5_digest=file_hashes["md5"],
            sha256_digest=file_hashes["sha256"],
            blake2_256_digest=file_hashes["blake2_256"],
            metadata_file_sha256_digest=metadata_file_hashes.get("sha256"),
            metadata_file_blake2_256_digest=metadata_file_hashes.get("blake2_256"),
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

        file_.record_event(
            tag=EventTag.File.FileAdd,
            request=request,
            additional={
                "filename": file_.filename,
                "submitted_by": (
                    request.user.username if request.user else "OpenID created token"
                ),
                "canonical_version": release.canonical_version,
                "publisher_url": (
                    request.oidc_publisher.publisher_url(request.oidc_claims)
                    if request.oidc_publisher
                    else None
                ),
                "project_id": str(project.id),
                "uploaded_via_trusted_publisher": bool(request.oidc_publisher),
            },
        )

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
                submitted_by=request.user if request.user else None,
            )
        )

        # If we have attestations from above, persist them.
        if attestations:
            request.db.add(
                integrity_service.build_provenance(request, file_, attestations)
            )

            # Log successful attestation upload
            request.metrics.increment("warehouse.upload.attestations.ok")

        # TODO: We need a better answer about how to make this transactional so
        #       this won't take affect until after a commit has happened, for
        #       now we'll just ignore it and save it before the transaction is
        #       committed.
        storage = request.find_service(IFileStorage, name="archive")
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

        if metadata_file_hashes:
            storage.store(
                file_.metadata_path,
                os.path.join(tmpdir, filename + ".metadata"),
                meta={
                    "project": file_.release.project.normalized_name,
                    "version": file_.release.version,
                    "package-type": file_.packagetype,
                    "python-version": file_.python_version,
                },
            )

    # For existing releases, we check if any of the existing project URLs are unverified
    # and have been verified in the current upload. In that case, we mark them as
    # verified.
    if not is_new_release and project_urls:
        for name, release_url in release._project_urls.items():
            if (
                not release_url.verified
                and name in project_urls
                and project_urls[name]["url"] == release_url.url
                and project_urls[name]["verified"]
            ):
                release_url.verified = True

        if home_page_verified and not release.home_page_verified:
            release.home_page_verified = True
        if download_url_verified and not release.download_url_verified:
            release.download_url_verified = True

    request.db.flush()  # flush db now so server default values are populated for celery

    # Push updates to BigQuery
    dist_metadata = {
        "metadata_version": meta.metadata_version,
        "name": meta.name,
        "version": str(meta.version),
        "summary": meta.summary,
        "description": (
            # Truncate the description by bytes and not characters if it is too long
            meta.description.encode()[
                :MAX_DESCRIPTION_LENGTH_TO_BIGQUERY_IN_BYTES
            ].decode("utf-8", "ignore")
            if meta.description is not None
            else None
        ),
        "author": meta.author,
        "description_content_type": meta.description_content_type,
        "author_email": meta.author_email,
        "maintainer": meta.maintainer,
        "maintainer_email": meta.maintainer_email,
        "license": meta.license,
        "license_expression": meta.license_expression,
        "license_files": meta.license_files,
        "keywords": ", ".join(meta.keywords) if meta.keywords else None,
        "classifiers": meta.classifiers,
        "platform": meta.platforms[0] if meta.platforms else None,
        "home_page": meta.home_page,
        "download_url": meta.download_url,
        "requires_python": (
            str(meta.requires_python) if meta.requires_python is not None else None
        ),
        "pyversion": form["pyversion"].data,
        "filetype": form["filetype"].data,
        "comment": form["comment"].data,
        "requires": meta.requires,
        "provides": meta.provides,
        "obsoletes": meta.obsoletes,
        "requires_dist": (
            [str(r) for r in meta.requires_dist] if meta.requires_dist else None
        ),
        "provides_dist": meta.provides_dist,
        "obsoletes_dist": meta.obsoletes_dist,
        "requires_external": meta.requires_external,
        "project_urls": (
            [", ".join([k, v]) for k, v in meta.project_urls.items()]
            if meta.project_urls is not None
            else None
        ),
        "filename": file_data.filename,
        "python_version": file_data.python_version,
        "packagetype": file_data.packagetype,
        "comment_text": file_data.comment_text,
        "size": file_data.size,
        "has_signature": False,
        "md5_digest": file_data.md5_digest,
        "sha256_digest": file_data.sha256_digest,
        "blake2_256_digest": file_data.blake2_256_digest,
        "path": file_data.path,
        "uploaded_via": file_data.uploaded_via,
        "upload_time": file_data.upload_time,
    }
    if request.registry.settings.get("warehouse.release_files_table") is not None:
        request.task(update_bigquery_release_files).delay(dist_metadata)

    # Log a successful upload
    request.metrics.increment(
        "warehouse.upload.ok", tags=[f"filetype:{form.filetype.data}"]
    )

    # Dispatch our task to sync this to cache as soon as possible
    request.task(sync_file_to_cache).delay(file_.id)

    # Return any warnings that we've accumulated as the response body.
    return HTTPOk(body="\n".join(warnings))


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
