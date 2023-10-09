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

import dataclasses
import enum
import hashlib
import hmac
import os.path
import io
import shutil
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
from warehouse.forklift.forms import UploadForm, SECURE_HASHES
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
from warehouse.utils.files import HashedFileWrapper, LimitedFileWrapper, FileLimitError
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


def _sanitize_request(request: Request) -> str | None:
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

    # Check if any fields were supplied as a tuple and have become a
    # FieldStorage. The 'content' field _should_ be a FieldStorage, however.
    # ref: https://github.com/pypi/warehouse/issues/2185
    # ref: https://github.com/pypi/warehouse/issues/2491
    for field in set(request.POST) - {"content", "gpg_signature"}:
        values = request.POST.getall(field)
        if any(isinstance(value, FieldStorage) for value in values):
            return f"{field}: Should not be a tuple."

    return None


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


@dataclasses.dataclass(frozen=True, kw_only=True, slots=True)
class UploadedFile:
    path: os.PathLike
    filename: str
    size: int
    digests: dict[str, str]


def _copy_uploaded_file(
    request: Request,
    tmpdir: os.PathLike,
    project: Project,
    filename: str,
    src: io.RawIOBase,
    *,
    digests: dict[str, str],
) -> UploadedFile:
    # The project may or may not have a file size specified on the project, if
    # it does then it may or may not be smaller or larger than our global file
    # size limits.
    file_size_limit = max(filter(None, [MAX_FILESIZE, project.upload_limit]))
    project_size_limit = max(filter(None, [MAX_PROJECT_SIZE, project.total_size_limit]))

    # We don't allow files of arbitrary size, so we wrap our file obj in a wrapper
    # that will ensure we respect our given limit.
    limited_file = LimitedFileWrapper(src, file_size_limit)

    # As we're copying the file to a local temporary file, we want to take this
    # opportunity to compute hashes for the uploaded file. To do this we'll wrap
    # our file with a wrapper that will opportunitistically update hashes as the
    # file is read.
    hashed_file = HashedFileWrapper(
        limited_file,
        {
            "md5": hashlib.md5(usedforsecurity=False),
            "sha256": hashlib.sha256(),
            "blake2_256": hashlib.blake2b(digest_size=256 // 8),
        },
    )

    # Actually copy the file to the destination.
    path = os.path.join(tmpdir, filename)
    try:
        with open(path, "rb") as dst:
            shutil.copyfileobj(hashed_file, dst)
    except FileLimitError:
        # If we've gotten a FileLimitError, then the size of the file is
        # too large and we need to bail out with a reasonable error message.
        raise _exc_with_message(
            HTTPBadRequest,
            (
                "File too large. Limit for project {name!r} is {limit} MB. "
                "See {url} for more information"
            ).format(
                name=project.name,
                limit=file_size_limit // ONE_MB,
                url=request.help_url(_anchor="file-size-limit"),
            ),
        ) from None

    # If the uploaded file pushes the project past it's total size limitat,
    # then we'll need to raise an error.
    if limited_file.amount_read + project.total_size > project_size_limit:
        raise _exc_with_message(
            HTTPBadRequest,
            (
                "Project size too large. Limit for project {name!r} total size is {limit} GB. "
                "See {url} for more information"
            ).format(
                name=project.name,
                limit=project_size_limit // ONE_GB,
                url=request.help_url(_anchor="project-size-limit"),
            ),
        )

    # Actually verify the digests that we've gotten. We're going to use
    # hmac.compare_digest even though we probably don't actually need to
    # because it's better safe than sorry. In the case of multiple digests
    # we expect them all to match.
    #
    # If the user didn't provide a value for a given hash algorith, then we
    # won't attempt to validate it.
    if not all(
        [
            hmac.compare_digest(digests[name].lower(), digest)
            for name, digest in hashed_file.digests.items()
            if name in digests
        ]
    ):
        raise _exc_with_message(
            HTTPBadRequest,
            "The digest supplied does not match a digest calculated "
            "from the uploaded file.",
        )

    # Return the captured metadata for the file
    return UploadedFile(
        path=path,
        filename=filename,
        size=limited_file.amount_read,
        digests=hashed_file.digests(),
    )


@dataclasses.dataclass(frozen=True, kw_only=True, slots=True)
class MetadataFile:
    path: os.PathLike
    filename: str
    size: int
    digests: dict[str, str]
    content: bytes


def _extract_and_copy_metadata(
    tmpdir: os.PathLike, artifact: UploadedFile
) -> MetadataFile | None:
    # Attempt to extract the metadata from our artifact
    if (metadata_contents := metadata.extract(artifact.path)) is not None:
        filename = f"{artifact.filename}.metadata"
        path = os.path.join(tmpdir, filename)

        # Write out the metadata file to our temporary location
        with open(path, "wb") as fp:
            fp.write(metadata_contents)

        return MetadataFile(
            path=path,
            filename=filename,
            size=len(metadata_contents),
            digests={
                "sha256": hashlib.sha256(metadata_contents).hexdigest().lower(),
                "blake2_256": (
                    hashlib.blake2b(metadata_contents, digest_size=256 // 8)
                    .hexdigest()
                    .lower()
                ),
            },
            content=metadata_contents,
        )

    return None


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


class ConflictResult(enum.Enum):
    # The filename does not conflict with existing or previous file.
    Ok = enum.auto()
    # The filename is an exact duplicate of an existing file.
    Duplicate = enum.auto()
    # The filename conflicts with an existing file.
    ConflictsExisting = enum.auto()
    # The filename conflicts with a previously used file.
    ConflictsPrevious = enum.auto()


def _check_filename_conflicts(db, filename, digests: dict[str, str]) -> ConflictResult:
    # Check if the filename matches a filename for any existing "live" file.
    if (file_ := db.query(File).filter(File.filename == filename).first()) is not None:
        # The filename matches an existing file, so we want to check if the existing
        # file and the new file are the same.
        #
        # To do this we require at least one secure hash to be passed in via digests,
        # which should be guarenteed because of our form validation, but we'll double
        # check. Then we'll take all of our digests for the incoming file, and check
        # them against the digests of the existing file.
        #
        # Since we're running this prior to having computed our own digests, we're
        # trusting the digests provided by the user. However this is safe, because
        # we're either going to no-op or error, and the only thing the user can do
        # by lying about the digest is either change a no-op to an error, or an error
        # to a no-op.
        if (digests.keys() & SECURE_HASHES) and all(
            [
                hmac.compare_digest(getattr(file_, f"{name}_digest"), value)
                for name, value in digests.items()
            ]
        ):
            return ConflictResult.Duplicate
        # If we either didn't have a secure hash somehow, or all of the digests
        # didn't match, then this is conflict.
        else:
            return ConflictResult.ConflictsExisting

    # Check if the filename was ever used by checking in our filename log, which
    # never gets expunged even if a file gets deleted.
    if db.query(
        db.query(Filename).filter(Filename.filename == filename).exists()
    ).scalar():
        # This is always a conflicts, because the file no longer exists
        return ConflictResult.ConflictsPrevious

    # We're OK, there's no conflict at all.
    return ConflictResult.Ok


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

    # We require protocol_version 1, it's the only supported version however
    # passing a different version should raise an error.
    if request.POST.get("protocol_version", "1") != "1":
        raise _exc_with_message(HTTPBadRequest, "Unknown protocol version.")

    # Sanitize the incoming request. There's a lot of garbage that gets sent to
    # this view, which we'll sanitize to clean that up and/or fail early rather
    # than getting failures deeper in the stack.
    #
    # NOTE: This method mutates the current request to do it's cleanup, but it
    #       can also return an error message if it could not sanitize.
    if (reason := _sanitize_request(request)) is not None:
        raise _exc_with_message(HTTPForbidden, reason)

    # Do some basic check to make sure that we're allowing uploads, either
    # generally or for the current identity. Wo do this first, before doing
    # anything else so that we can bail out early if there's no chance we're
    # going to accept the upload anyways.
    if (reason := _upload_disallowed(request)) is not None:
        raise _exc_with_message(HTTPForbidden, reason)

    # Validate the non Metadata portions of the upload data
    form = UploadForm(request.POST)
    if not form.validate():
        raise _exc_with_message(HTTPBadRequest, "FIXME: A Real Error Message")

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

    # Validate the filename against our existing data, checking to see if it
    # matches any already used filenames or not.
    #
    # We do this here, rather than earlier so that we don't leak any information
    # about a project's files until we've verified that the user has permission
    # to upload. In theory this shouldn't matter, since all of our files are
    # public anyways, but better safe than sorry.
    match _check_filename_conflicts(request.db, form.filename.data, form.digests):
        case ConflictResult.Duplicate:
            # It's very important that we doom the transaction here, we're trusting
            # the digests provided by the user rather than generating them ourselves,
            # so we want to be very sure that nothing that happens in this request
            # will effect the database, because that will ensure that this case is
            # only ever a no-op or an error.
            request.tm.doom()
            return Response()
        case ConflictResult.ConflictsExisting:
            help_url = request.help_url(_anchor="file-name-reuse")
            reason = f"File already exists. See {help_url} for more information."
            _exc_with_message(HTTPBadRequest, reason)
        case ConflictResult.ConflictsPrevious:
            help_url = request.help_url(_anchor="file-name-reuse")
            reason = (
                "This filename has already been used, use a different version. "
                f"See {help_url} for more information."
            )
            _exc_with_message(HTTPBadRequest, reason)
        case ConflictResult.Ok:
            pass

    # We're going to need a temporary, request scoped, location to buffer uploaded
    # data to disk so that we don't have to buffer in memory, so we'll create a
    # temporary directory and register a callback that will clean it up when the
    # request has completed.
    #
    # NOTE: request.add_finished_callback callbacks are called unconditionally
    #       whether the request is successful or not, thus this is similiar to
    #       using this as a context manager, except scoped to the life of the
    #       request.
    tmpdir = tempfile.TemporaryDirectory()
    request.add_finished_callback(lambda _: tmpdir.cleanup())

    # Copy the uploaded file to a temporary location, allowing us to compute the
    # hashes, check the upload size, extract the metadata, etc.
    uploaded_file = _copy_uploaded_file(
        request,
        tmpdir,
        project,
        form.filename.data,
        request.POST["content"].file,
        digests=form.digests,
    )

    # Check the file to make sure it is a valid distribution file.
    if not _is_valid_dist_file(uploaded_file.path, form.filetype.data):
        raise _exc_with_message(HTTPBadRequest, "Invalid distribution file.")

    # Extract the METADATA file out of the uploaded file.
    try:
        metadata_file = _extract_and_copy_metadata(tmpdir, uploaded_file)
    except metadata.InvalidArtifact as exc:
        raise _exc_with_message(HTTPBadRequest, exc.reason)

    # Parse whatever metadata we have, preferring metadata extracted out of the
    # artifact, but falling back to the metadata provided in the POST data
    # otherwise.
    #
    # TODO: Probably at some point we want to require the use of metadata that
    #       we can extract from a distribution and get rid of the fallback to
    #       form based metadata.
    try:
        meta = metadata.parse(metadata_file.content, form_data=request.POST)
    except packaging.metadata.InvalidMetadata as exc:
        raise  # FIXME: Better error handling

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
        # canonical version equivalence.
        #
        # We've been doing this for so long now, that we're going to treat this
        # as an error. Projects hitting this at this point should create a new
        # release or delete an old release or something.
        raise _exc_with_message(
            HTTPBadRequest,
            f"Multiple distinct versions found for {canonical_version} of {project.name}. "
            "These versions are in a bad state which is no longer possible. "
            "Try releasing as a new version.",
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
            # FIXME:
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

    # Check to see if uploading this file would create a duplicate sdist
    # for the current release.
    #
    # TODO: Once we no longer support uploading .zip files for sdists then we
    #       can get rid of this check and the standard duplicate file check will
    #       cover it.
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

    # TODO: This should be handled by some sort of database trigger or a
    #       SQLAlchemy hook or the like instead of doing it inline in this
    #       view.
    request.db.add(Filename(filename=uploaded_file.filename))

    # Store the information about the file in the database.
    file_ = File(
        release=release,
        filename=uploaded_file.filename,
        python_version=form.pyversion.data,
        packagetype=form.filetype.data,
        comment_text=form.comment.data,
        size=uploaded_file.size,
        md5_digest=uploaded_file.digests["md5"],
        sha256_digest=uploaded_file.digests["sha256"],
        blake2_256_digest=uploaded_file.digests["blake2_256"],
        # Figure out what our filepath is going to be, we're going to use a
        # directory structure based on the hash of the file contents. This
        # will ensure that the contents of the file cannot change without
        # it also changing the path that the file is saved too.
        path="/".join(
            [
                uploaded_file.digests[PATH_HASHER][:2],
                uploaded_file.digests[PATH_HASHER][2:4],
                uploaded_file.digests[PATH_HASHER][4:],
                uploaded_file.filename,
            ]
        ),
        uploaded_via=request.user_agent,
    )

    # TODO: Once we are in a world where we *only* support artifacts that we can
    #       extract the metadata from, then we can make this no longer conditional.
    if metadata_file is not None:
        file_.metadata_file_sha256_digest = metadata_file.digests["sha256"]
        file_.metadata_file_blake2_256_digest = metadata_file.digests["blake2_256"]

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
            "publisher_url": request.oidc_publisher.publisher_url(request.oidc_claims)
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
        uploaded_file.path,
        meta={
            "project": file_.release.project.normalized_name,
            "version": file_.release.version,
            "package-type": file_.packagetype,
            "python-version": file_.python_version,
        },
    )

    # TODO: Once we are in a world where we *only* support artifacts that we can
    #       extract the metadata from, then we can make this no longer conditional.
    if metadata_file is not None:
        storage.store(
            file_.metadata_path,
            metadata_file.path,
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
        "platform": meta.platforms[0],  # FIXME: This is a multi-use field
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
        "project_urls": meta.project_urls,  # FIXME: Make sure this can handle mapping
        # File Data
        # FIXME: Figure out which fields the BigQuery table even has
        # "pyversion": form["pyversion"].data,
        # "filetype": form["filetype"].data,
        # "comment": form["comment"].data,
        "filename": file_.filename,
        "python_version": file_.python_version,
        "packagetype": file_.packagetype,
        "comment_text": file_.comment_text,
        "size": file_.size,
        "has_signature": False,
        "md5_digest": file_.md5_digest,
        "sha256_digest": file_.sha256_digest,
        "blake2_256_digest": file_.blake2_256_digest,
        "path": file_.path,
        "uploaded_via": file_.uploaded_via,
        "upload_time": file_.upload_time,
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
