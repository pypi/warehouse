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

import hashlib
import hmac
import os.path
import re
import tarfile
import tempfile
import zipfile

from cgi import FieldStorage

import packaging.metadata
import packaging.requirements
import packaging.specifiers
import packaging.utils
import packaging.version
import packaging_legacy.version
import sentry_sdk

from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPException,
    HTTPForbidden,
    HTTPGone,
    HTTPPermanentRedirect,
    HTTPTooManyRequests,
)
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy import func, orm
from sqlalchemy.exc import MultipleResultsFound, NoResultFound

from warehouse.admin.flags import AdminFlagValue
from warehouse.classifiers.models import Classifier
from warehouse.email import (
    send_basic_auth_with_two_factor_email,
    send_gpg_signature_uploaded_email,
    send_two_factor_not_yet_enabled_email,
)
from warehouse.errors import BasicAuthTwoFactorEnabled
from warehouse.events.tags import EventTag
from warehouse.forklift import metadata
from warehouse.forklift.forms import UploadForm
from warehouse.metrics import IMetricsService
from warehouse.packaging.interfaces import IFileStorage, IProjectService
from warehouse.packaging.models import (
    Dependency,
    DependencyKind,
    Description,
    File,
    Filename,
    JournalEntry,
    Project,
    Release,
)
from warehouse.packaging.tasks import sync_file_to_cache, update_bigquery_release_files
from warehouse.rate_limiting.interfaces import RateLimiterException
from warehouse.utils import readme
from warehouse.utils.project import validate_project_name
from warehouse.utils.security_policy import AuthenticationMethod

ONE_MB = 1 * 1024 * 1024
ONE_GB = 1 * 1024 * 1024 * 1024

MAX_FILESIZE = 100 * ONE_MB
MAX_SIGSIZE = 8 * 1024
MAX_PROJECT_SIZE = 10 * ONE_GB

PATH_HASHER = "blake2_256"

COMPRESSION_RATIO_MIN_SIZE = 64 * ONE_MB

# If the zip file decompressed to 50x more space
# than it is uncompressed, consider it a ZIP bomb.
# Note that packages containing interface descriptions, JSON,
# such resources can compress really well.
# See discussion here: https://github.com/pypi/warehouse/issues/13962
COMPRESSION_RATIO_THRESHOLD = 50


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


def _exc_with_message(exc, message, **kwargs):
    # The crappy old API that PyPI offered uses the status to pass down
    # messages to the client. So this function will make that easier to do.
    resp = exc(detail=message, **kwargs)
    # We need to guard against characters outside of iso-8859-1 per RFC.
    # Specifically here, where user-supplied text may appear in the message,
    # which our WSGI server may not appropriately handle (indeed gunicorn does not).
    status_message = message.encode("iso-8859-1", "replace").decode("iso-8859-1")
    resp.status = f"{resp.status_code} {status_message}"
    return resp


def _construct_dependencies(
    meta: packaging.metadata.Metadata, types: dict[str, DependencyKind]
) -> list[Dependency]:
    result = []
    for name, kind in types.items():
        for item in getattr(meta, name):
            yield Dependency(kind=kind.value, specifier=str(item))
    return result


def _upload_disallowed(request: Request) -> str | None:
    # If we're in read-only mode, let upload clients know
    if request.flags.enabled(AdminFlagValue.READ_ONLY):
        return "Read-only mode: Uploads are temporarily disabled."

    if request.flags.enabled(AdminFlagValue.DISALLOW_NEW_UPLOAD):
        return (
            "New uploads are temporarily disabled. "
            "See {projecthelp} for more information.".format(
                projecthelp=request.help_url(_anchor="admin-intervention")
            )
        )

    # If there isn't an authenticated identity with this request, then we can't
    # upload anyways.
    if request.identity is None:
        return (
            "Invalid or non-existent authentication information. "
            "See {projecthelp} for more information.".format(
                projecthelp=request.help_url(_anchor="invalid-auth")
            )
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
            return (
                "User {!r} does not have a verified primary email address. "
                "Please add a verified primary email before attempting to "
                "upload to PyPI. See {project_help} for more information."
            ).format(
                request.user.username,
                project_help=request.help_url(_anchor="verified-email"),
            )

    return None


def _get_or_create_project(request: Request, project_name: str) -> Project:
    # Look up the project first before doing anything else, this is so we can
    # automatically register it if we need to and can check permissions before
    # going any further.
    project = (
        request.db.query(Project)
        .filter(Project.normalized_name == func.normalize_pep426_name(project_name))
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
        try:
            validate_project_name(project_name, request)
        except HTTPException as exc:
            raise _exc_with_message(exc.__class__, exc.detail) from None

        project_service = request.find_service(IProjectService)
        try:
            project = project_service.create_project(
                project_name, request.user, request
            )
        except RateLimiterException:
            msg = "Too many new projects created"
            raise _exc_with_message(HTTPTooManyRequests, msg)

    return project


def _invalid_filename_for_metadata(
    filename: str, meta: packaging.metadata.Metadata
) -> str | None:
    # Extract the project name from the filename and normalize it.
    filename_prefix = (
        # For wheels, the project name is normalized and won't contain hyphens, so
        # we can split on the first hyphen.
        filename.partition("-")[0]
        if filename.endswith(".whl")
        # For source releases, we know that the version should not contain any
        # hyphens, so we can split on the last hyphen to get the project name.
        else filename.rpartition("-")[0]
    )

    # Normalize the prefix in the filename. Eventually this should be unnecessary once
    # we become more restrictive in what we permit
    filename_prefix = filename_prefix.lower().replace(".", "_").replace("-", "_")

    # Make sure that our filename matches the project that it is being uploaded to.
    if (
        prefix := packaging.utils.canonicalize_name(meta.name).replace("-", "_")
    ) != filename_prefix:
        raise _exc_with_message(
            HTTPBadRequest,
            f"Start filename for {meta.name!r} with {prefix!r}.",
        )


def _is_valid_dist_file(filename, filetype):
    """
    Perform some basic checks to see whether the indicated file could be
    a valid distribution file.
    """

    # If our file is a zipfile, then ensure that it's members are only
    # compressed with supported compression methods.
    if zipfile.is_zipfile(filename):
        # Ensure the compression ratio is not absurd (decompression bomb)
        compressed_size = os.stat(filename).st_size
        with zipfile.ZipFile(filename) as zfp:
            decompressed_size = sum(e.file_size for e in zfp.infolist())
        if (
            decompressed_size > COMPRESSION_RATIO_MIN_SIZE
            and decompressed_size / compressed_size > COMPRESSION_RATIO_THRESHOLD
        ):
            sentry_sdk.capture_message(
                f"File {filename} ({filetype}) exceeds compression ratio "
                f"of {COMPRESSION_RATIO_THRESHOLD} "
                f"({decompressed_size}/{compressed_size})"
            )
            return False

        # Check that the compression type is valid
        with zipfile.ZipFile(filename) as zfp:
            for zinfo in zfp.infolist():
                if zinfo.compress_type not in {
                    zipfile.ZIP_STORED,
                    zipfile.ZIP_DEFLATED,
                }:
                    return False

    if filename.endswith(".tar.gz"):
        # TODO: Ideally Ensure the compression ratio is not absurd
        # (decompression bomb), like we do for wheel/zip above.

        # Ensure that this is a valid tar file, and that it contains PKG-INFO.
        try:
            with tarfile.open(filename, "r:gz") as tar:
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
        except (tarfile.ReadError, EOFError):
            return False
    elif filename.endswith(".zip"):
        # Ensure that the .zip is a valid zip file, and that it has a
        # PKG-INFO file.
        try:
            with zipfile.ZipFile(filename, "r") as zfp:
                for zipname in zfp.namelist():
                    parts = os.path.split(zipname)
                    if len(parts) == 2 and parts[1] == "PKG-INFO":
                        # We need the no branch below to work around a bug in
                        # coverage.py where it's detecting a missed branch
                        # where there isn't one.
                        break
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
                        break
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
    # This is a list of warnings that we'll emit *IF* the request is successful.
    warnings = []

    # Log an attempt to upload
    metrics = request.find_service(IMetricsService, context=None)
    metrics.increment("warehouse.upload.attempt")

    # Do some basic check to make sure that we're allowing uploads, either
    # generally or for the current identity. Wo do this first, before doing
    # anything else so that we can bail out early if there's no chance we're
    # going to accept the upload anyways.
    if (reason := _upload_disallowed(request)) is not None:
        raise _exc_with_message(HTTPForbidden, reason)

    # Do some cleanup of the various form fields, there's a lot of garbage that
    # gets sent to this view, and this helps prevent issues later on.
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
    # FieldStorage. The 'content' field _should_ be a FieldStorage, however.
    # ref: https://github.com/pypi/warehouse/issues/2185
    # ref: https://github.com/pypi/warehouse/issues/2491
    for field in set(request.POST) - {"content", "gpg_signature"}:
        values = request.POST.getall(field)
        if any(isinstance(value, FieldStorage) for value in values):
            raise _exc_with_message(HTTPBadRequest, f"{field}: Should not be a tuple.")

    # Ensure that we have file data in the request.
    if "content" not in request.POST:
        raise _exc_with_message(HTTPBadRequest, "Upload payload does not have a file.")

    # Validate the non Metadata portions of the upload data
    form = UploadForm(request.POST)
    if not form.validate():
        raise _exc_with_message(HTTPBadRequest, "TODO: A Real Error Message")

    # At this point, we've validated that we have a file upload, and we know
    # what project it is for, and we've validated that the project name is a
    # valid project name.
    #
    # In order to continue on, we need to fetch the Project from the database,
    # creating it if it doesn't exist, because we want to check permissions
    # before continuing on and we also need to know things like what the upload
    # limit is for this project before we can start consuming the file that is
    # being uploaded.
    project = _get_or_create_project(request, form.name.data)

    # Check that the identity has permission to do things to this project, if this
    # is a new project this will act as a sanity check for the role we just
    # added above.
    allowed = request.has_permission("upload", project)
    if not allowed:
        reason = getattr(allowed, "reason", None)
        identity = f"user {request.user.username!r}" if request.user else "token"
        raise _exc_with_message(
            HTTPForbidden,
            (
                "The {identity} isn't allowed to upload to the project {project!r}. "
                "See {url} for more information."
            ).format(
                identity=identity,
                project=project.name,
                url=request.help_url("project-name"),
            ),
        )

    # Check if the user has 2FA and used basic auth
    # NOTE: We don't need to guard request.user here because basic auth
    # can only be used with user identities.
    if (
        request.authentication_method == AuthenticationMethod.BASIC_AUTH
        and request.user.has_two_factor
    ):
        send_basic_auth_with_two_factor_email(
            request, request.user, project_name=project.name
        )
        raise _exc_with_message(
            BasicAuthTwoFactorEnabled,
            (
                f"User { request.user.username } has two factor auth enabled, "
                "an API Token or Trusted Publisher must be used to upload "
                "in place of password."
            ),
        )

    # Fetch and validate the incoming metadata, ensuring that it is fully
    # validated by the packaging.metdata.
    try:
        meta = metadata.load(form_data=request.POST)
    except packaging.metadata.InvalidMetadata as exc:
        raise  # TODO: Better error handling

    # We validate that the filename is valid given the project name and version
    # that we have parsed out of the metadata.
    if (reason := _invalid_filename_for_metadata(form.filename.data, meta)) is not None:
        raise _exc_with_message(HTTPBadRequest, reason)

    # Update name if it differs but is still equivalent. We don't need to check if
    # they are equivalent when normalized because that's already been done when we
    # queried for the project.
    if project.name != meta.name:
        project.name = meta.name

    # Render our description so we can save from having to render this data every time
    # we load a project description page.
    rendered = None
    if meta.description:
        description_content_type = meta.description_content_type
        if not description_content_type:
            description_content_type = "text/x-rst"

        rendered = readme.render(
            meta.description, description_content_type, use_fallback=False
        )

        # Uploading should prevent broken rendered descriptions.
        if rendered is None:
            if meta.description_content_type:
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
        # TODO: Handle?
        release = (
            request.db.query(Release)
            .filter(
                (Release.project == project) & (Release.version == form.version.data)
            )
            .one()
        )
    except NoResultFound:
        # Get all the classifiers for this release
        release_classifiers = (
            request.db.query(Classifier)
            .filter(Classifier.classifier.in_(meta.classifiers))
            .all()
        )

        release = Release(
            project=project,
            _classifiers=release_classifiers,
            dependencies=_construct_dependencies(
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
            ),
            canonical_version=canonical_version,
            description=Description(
                content_type=meta.description_content_type,
                raw=meta.description or "",
                html=rendered or "",
                rendered_by=readme.renderer_version(),
            ),
            # TODO: Fixes
            #  - keywords: Turn from string field into list field
            #  - platform: Rename to platforms, turn from string field into list field
            #  - Add supported_platforms
            #  - Add metadata_version
            #  - Add provides_extra
            #  - Validate metadata_version
            **{
                k: str(getattr(meta, k))
                for k in {
                    # This is a list of all the fields in the metadata that we
                    # should pull off and insert into our new release, that didn't
                    # require special handling up above.
                    # Metadata 1.0 - PEP 241
                    "metadata_version",
                    "author",
                    "author_email",
                    "home_page",
                    "keywords",
                    "license",
                    "platforms",
                    "summary",
                    "version",
                    # Metadata 1.1 - PEP 314
                    "download_url",
                    "supported_platforms",
                    # Metadata 1.2 - PEP 345
                    "maintainer",
                    "maintainer_email",
                    "project_urls",
                    "requires_python",
                    # Metadata 2.1 - PEP 566
                    "provides_extra",
                }
            },
            uploader=request.user if request.user else None,
            uploaded_via=request.user_agent,
        )
        request.db.add(release)

        if "gpg_signature" in request.POST:
            warnings.append(
                "GPG signature support has been removed from PyPI and the "
                "provided signature has been discarded."
            )
            send_gpg_signature_uploaded_email(
                request, request.user, project_name=project.name
            )

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
                "submitted_by": request.user.username
                if request.user
                else "OpenID created token",
                "canonical_version": release.canonical_version,
                "publisher_url": request.oidc_publisher.publisher_url(
                    request.oidc_claims
                )
                if request.oidc_publisher
                else None,
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
        sorted(releases, key=lambda x: packaging_legacy.version.parse(x.version))
    ):
        r._pypi_ordering = i

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

    # TODO: Remove this, or figure out a better location for it.
    filename = form.filename.data

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
                            name=project.name, limit=project_size_limit // ONE_GB
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
                    getattr(form, f"{digest_name}_digest").data.lower(),
                    digest_value,
                )
                for digest_name, digest_value in file_hashes.items()
                if getattr(form, f"{digest_name}_digest").data
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
            request.tm.doom()
            return Response()
        elif is_duplicate is not None:
            raise _exc_with_message(
                HTTPBadRequest,
                # Note: Changing this error message to something that doesn't
                # start with "File already exists" will break the
                # --skip-existing functionality in twine
                # ref: https://github.com/pypi/warehouse/issues/3482
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
            try:
                _, __, ___, tags = packaging.utils.parse_wheel_filename(filename)
            except packaging.utils.InvalidWheelFilename as e:
                raise _exc_with_message(
                    HTTPBadRequest,
                    str(e),
                )

            for tag in tags:
                if not _valid_platform_tag(tag.platform):
                    raise _exc_with_message(
                        HTTPBadRequest,
                        f"Binary wheel '{filename}' has an unsupported "
                        f"platform tag '{tag.platform}'.",
                    )

            """
            Extract METADATA file from a wheel and return it as a content.
            The name of the .whl file is used to find the corresponding .dist-info dir.
            See https://peps.python.org/pep-0491/#file-contents
            """
            filename = os.path.basename(temporary_filename)
            # Get the name and version from the original filename. Eventually this
            # should use packaging.utils.parse_wheel_filename(filename), but until then
            # we can't use this as it adds additional normailzation to the project name
            # and version.
            name, version, _ = filename.split("-", 2)
            metadata_filename = f"{name}-{version}.dist-info/METADATA"
            try:
                with zipfile.ZipFile(temporary_filename) as zfp:
                    wheel_metadata_contents = zfp.read(metadata_filename)
            except KeyError:
                raise _exc_with_message(
                    HTTPBadRequest,
                    "Wheel '{filename}' does not contain the required "
                    "METADATA file: {metadata_filename}".format(
                        filename=filename, metadata_filename=metadata_filename
                    ),
                )
            with open(temporary_filename + ".metadata", "wb") as fp:
                fp.write(wheel_metadata_contents)
            metadata_file_hashes = {
                "sha256": hashlib.sha256(),
                "blake2_256": hashlib.blake2b(digest_size=256 // 8),
            }
            for hasher in metadata_file_hashes.values():
                hasher.update(wheel_metadata_contents)
            metadata_file_hashes = {
                k: h.hexdigest().lower() for k, h in metadata_file_hashes.items()
            }

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
                "submitted_by": request.user.username
                if request.user
                else "OpenID created token",
                "canonical_version": release.canonical_version,
                "publisher_url": request.oidc_publisher.publisher_url(
                    request.oidc_claims
                )
                if request.oidc_publisher
                else None,
                "project_id": str(project.id),
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

    # Check if the user has any 2FA methods enabled, and if not, email them.
    if request.user and not request.user.has_two_factor:
        warnings.append("Two factor authentication is not enabled for your account.")
        send_two_factor_not_yet_enabled_email(request, request.user)

    request.db.flush()  # flush db now so server default values are populated for celery

    # Push updates to BigQuery
    dist_metadata = {
        # Metadata
        "metadata_version": meta.metadata_version,
        "name": meta.name,
        "version": str(meta.version),
        "summary": meta.summary,
        "description": meta.description,
        "author": meta.author,
        "description_content_type": meta.description_content_type,
        "author_email": meta.author_email,
        "maintainer": meta.maintainer,
        "maintainer_email": meta.maintainer_email,
        "license": meta.license,
        "keywords": meta.keywords,
        "classifiers": meta.classifiers,
        "platform": meta.platforms[0],  # TODO: This is a multi-use field
        "home_page": meta.home_page,
        "download_url": meta.download_url,
        "requires_python": meta.requires_python,
        "requires": meta.requires,
        "provides": meta.provides,
        "obsoletes": meta.obsoletes,
        "requires_dist": [str(r) for r in meta.requires_dist],
        "provides_dist": meta.provides_dist,
        "obsoletes_dist": meta.obsoletes_dist,
        "requires_external": meta.requires_external,
        "project_urls": meta.project_urls,  # TODO: Make sure this can handle mapping
        # File Data
        # TODO: Figure out which fields the BigQuery table even has
        # "pyversion": form["pyversion"].data,
        # "filetype": form["filetype"].data,
        # "comment": form["comment"].data,
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
    if not request.registry.settings.get("warehouse.release_files_table") is None:
        request.task(update_bigquery_release_files).delay(dist_metadata)

    # Log a successful upload
    metrics.increment("warehouse.upload.ok", tags=[f"filetype:{form.filetype.data}"])

    # Dispatch our task to sync this to cache as soon as possible
    request.task(sync_file_to_cache).delay(file_.id)

    # Return any warnings that we've accumulated as the response body.
    return Response("\n".join(warnings))


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
