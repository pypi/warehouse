# SPDX-License-Identifier: Apache-2.0

import collections
import hashlib
import io
import json
import logging
import os.path
import shutil
import warnings

from itertools import chain

import b2sdk.v2.exception
import botocore.exceptions
import google.api_core.exceptions
import google.api_core.retry
import sentry_sdk
import stdlib_list

from packaging.utils import canonicalize_name
from pyramid.httpexceptions import HTTPBadRequest, HTTPConflict, HTTPForbidden
from sqlalchemy import exists, func, select
from zope.interface import implementer

from warehouse.admin.flags import AdminFlagValue
from warehouse.cache import IQueryResultsCache
from warehouse.email import send_pending_trusted_publisher_invalidated_email
from warehouse.events.tags import EventTag
from warehouse.helpdesk.interfaces import IAdminNotificationService
from warehouse.metrics import IMetricsService
from warehouse.oidc.models import PendingOIDCPublisher
from warehouse.organizations.models import OrganizationProject
from warehouse.packaging.interfaces import (
    IDocsStorage,
    IFileStorage,
    IProjectService,
    ISimpleStorage,
    ProjectNameUnavailableExistingError,
    ProjectNameUnavailableInvalidError,
    ProjectNameUnavailableProhibitedError,
    ProjectNameUnavailableSimilarError,
    ProjectNameUnavailableStdlibError,
    ProjectNameUnavailableTypoSquattingError,
    TooManyProjectsCreated,
)
from warehouse.packaging.models import (
    JournalEntry,
    ProhibitedProjectName,
    Project,
    Role,
)
from warehouse.packaging.typosnyper import typo_check_name
from warehouse.rate_limiting import DummyRateLimiter, IRateLimiter
from warehouse.utils.exceptions import DevelopmentModeWarning
from warehouse.utils.project import PROJECT_NAME_RE

logger = logging.getLogger(__name__)


def _namespace_stdlib_list(module_list):
    for module_name in module_list:
        parts = module_name.split(".")
        for i, part in enumerate(parts):
            yield ".".join(parts[: i + 1])


STDLIB_PROHIBITED = {
    canonicalize_name(s.rstrip("-_.").lstrip("-_."))
    for s in chain.from_iterable(
        _namespace_stdlib_list(stdlib_list.stdlib_list(version))
        for version in stdlib_list.short_versions
    )
}


class InsecureStorageWarning(DevelopmentModeWarning):
    pass


class GenericLocalBlobStorage:
    def __init__(self, base):
        # This class should not be used in production, it's trivial for it to
        # be used to read arbitrary files from the disk. It is intended ONLY
        # for local development with trusted users. To make this clear, we'll
        # raise a warning.
        warnings.warn(
            "LocalFileStorage is intended only for use in development, you "
            "should not use it in production due to the lack of safe guards "
            "for safely locating files on disk.",
            InsecureStorageWarning,
        )

        self.base = base

    @classmethod
    def create_service(cls, context, request):
        raise NotImplementedError

    def get(self, path):
        return open(os.path.join(self.base, path), "rb")

    def get_metadata(self, path):
        return json.loads(open(os.path.join(self.base, path + ".meta")).read())

    def get_checksum(self, path):
        return hashlib.md5(
            open(os.path.join(self.base, path), "rb").read(), usedforsecurity=False
        ).hexdigest()

    def store(self, path, file_path, *, meta=None):
        destination = os.path.join(self.base, path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as dest_fp:
            with open(file_path, "rb") as src_fp:
                dest_fp.write(src_fp.read())
        if meta is not None:
            with open(destination + ".meta", "w") as dest_fp:
                dest_fp.write(json.dumps(meta))


@implementer(IFileStorage)
class LocalFileStorage(GenericLocalBlobStorage):
    @classmethod
    def create_service(cls, context, request):
        return cls(request.registry.settings["files.path"])


@implementer(IFileStorage)
class LocalArchiveFileStorage(GenericLocalBlobStorage):
    @classmethod
    def create_service(cls, context, request):
        return cls(request.registry.settings["archive_files.path"])


@implementer(ISimpleStorage)
class LocalSimpleStorage(GenericLocalBlobStorage):
    @classmethod
    def create_service(cls, context, request):
        return cls(request.registry.settings["simple.path"])


@implementer(IDocsStorage)
class LocalDocsStorage:
    def __init__(self, base):
        # This class should not be used in production, it's trivial for it to
        # be used to read arbitrary files from the disk. It is intended ONLY
        # for local development with trusted users. To make this clear, we'll
        # raise a warning.
        warnings.warn(
            "LocalDocsStorage is intended only for use in development, you "
            "should not use it in production due to the lack of safe guards "
            "for safely locating files on disk.",
            InsecureStorageWarning,
        )

        self.base = base

    @classmethod
    def create_service(cls, context, request):
        return cls(request.registry.settings["docs.path"])

    def remove_by_prefix(self, prefix):
        directory = os.path.join(self.base, prefix)
        try:
            shutil.rmtree(directory)
        except FileNotFoundError:
            pass


class GenericBlobStorage:
    def __init__(self, bucket, *, prefix: str | None = None):
        self.bucket = bucket
        self.prefix = prefix

    def _get_path(self, path: str) -> str:
        # If we have a prefix, then prepend it to our path. This will let us
        # store items inside of a sub directory without exposing that to end
        # users.
        if self.prefix:
            path = self.prefix + path

        return path


class GenericB2BlobStorage(GenericBlobStorage):
    def get(self, path: str):
        path = self._get_path(path)
        try:
            file_obj = io.BytesIO()
            downloaded_file = self.bucket.download_file_by_name(path)
            downloaded_file.save(file_obj)
            file_obj.seek(0)
            return file_obj
        except b2sdk.v2.exception.FileNotPresent:
            raise FileNotFoundError(f"No such key: {path!r}") from None

    def get_metadata(self, path: str):
        path = self._get_path(path)
        try:
            return self.bucket.get_file_info_by_name(path).file_info
        except b2sdk.v2.exception.FileNotPresent:
            raise FileNotFoundError(f"No such key: {path!r}") from None

    def get_checksum(self, path: str):
        path = self._get_path(path)
        try:
            return self.bucket.get_file_info_by_id(
                self.bucket.get_file_info_by_name(path).id_
            ).content_md5
        except b2sdk.v2.exception.FileNotPresent:
            raise FileNotFoundError(f"No such key: {path!r}") from None

    def store(self, path: str, file_path, *, meta=None):
        path = self._get_path(path)
        self.bucket.upload_local_file(
            local_file=file_path,
            file_name=path,
            file_infos=meta,
        )


@implementer(IFileStorage)
class B2FileStorage(GenericB2BlobStorage):
    @classmethod
    def create_service(cls, context, request):
        b2_api = request.find_service(name="b2.api")
        bucket = b2_api.get_bucket_by_name(request.registry.settings["files.bucket"])
        prefix = request.registry.settings.get("files.prefix")
        return cls(bucket, prefix=prefix)


class GenericS3BlobStorage(GenericBlobStorage):
    def get(self, path: str):
        # Note: this is not actually used to serve files, instead our CDN is
        # configured to connect directly to our storage bucket. See:
        # https://github.com/python/pypi-infra/blob/master/terraform/file-hosting/vcl/main.vcl
        try:
            return self.bucket.Object(self._get_path(path)).get()["Body"]
        except botocore.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchKey":
                raise
            raise FileNotFoundError(f"No such key: {path!r}") from None

    def get_metadata(self, path: str):
        try:
            return self.bucket.Object(self._get_path(path)).metadata
        except botocore.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchKey":
                raise
            raise FileNotFoundError(f"No such key: {path!r}") from None

    def get_checksum(self, path: str):
        try:
            return (
                self.bucket.Object(self._get_path(path)).e_tag.rstrip('"').lstrip('"')
            )
        except botocore.exceptions.ClientError as exc:
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
                #  https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html#API_HeadObject_RequestBody
                raise
            raise FileNotFoundError(f"No such key: {path!r}") from None

    def store(self, path: str, file_path, *, meta=None):
        extra_args = {}
        if meta is not None:
            extra_args["Metadata"] = meta

        path = self._get_path(path)

        self.bucket.upload_file(file_path, path, ExtraArgs=extra_args)


@implementer(IFileStorage)
class S3FileStorage(GenericS3BlobStorage):
    @classmethod
    def create_service(cls, context, request):
        session = request.find_service(name="aws.session")
        s3 = session.resource("s3")
        bucket = s3.Bucket(request.registry.settings["files.bucket"])
        prefix = request.registry.settings.get("files.prefix")
        return cls(bucket, prefix=prefix)


@implementer(IFileStorage)
class S3ArchiveFileStorage(GenericS3BlobStorage):
    @classmethod
    def create_service(cls, context, request):
        session = request.find_service(name="aws.session")
        s3 = session.resource("s3")
        bucket = s3.Bucket(request.registry.settings["archive_files.bucket"])
        prefix = request.registry.settings.get("archive_files.prefix")
        return cls(bucket, prefix=prefix)


@implementer(IDocsStorage)
class S3DocsStorage:
    def __init__(self, s3_client, bucket_name, *, prefix=None):
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.prefix = prefix

    @classmethod
    def create_service(cls, context, request):
        session = request.find_service(name="aws.session")
        s3_client = session.client("s3")
        bucket_name = request.registry.settings["docs.bucket"]
        prefix = request.registry.settings.get("docs.prefix")
        return cls(s3_client, bucket_name, prefix=prefix)

    def remove_by_prefix(self, prefix):
        if self.prefix:
            prefix = os.path.join(self.prefix, prefix)
        keys_to_delete = []
        keys = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
        for key in keys.get("Contents", []):
            keys_to_delete.append({"Key": key["Key"]})
            if len(keys_to_delete) > 99:
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name, Delete={"Objects": keys_to_delete}
                )
                keys_to_delete = []
        if len(keys_to_delete) > 0:
            self.s3_client.delete_objects(
                Bucket=self.bucket_name, Delete={"Objects": keys_to_delete}
            )


class GenericGCSBlobStorage(GenericBlobStorage):
    def get(self, path: str):
        # Note: this is not actually used in to serve files, instead our CDN is
        # configured to connect directly to our storage bucket. See:
        # https://github.com/python/pypi-infra/blob/master/terraform/file-hosting/vcl/main.vcl
        raise NotImplementedError

    def get_metadata(self, path: str):
        raise NotImplementedError

    def get_checksum(self, path: str):
        raise NotImplementedError

    @google.api_core.retry.Retry(
        predicate=google.api_core.retry.if_exception_type(
            google.api_core.exceptions.ServiceUnavailable
        )
    )
    def store(self, path: str, file_path, *, meta=None):
        path = self._get_path(path)
        blob = self.bucket.blob(path)
        if meta is not None:
            blob.metadata = meta

        # Our upload is not fully transactional, meaning that this upload may
        # succeed, and the corresponding write to DB may fail. If/when that
        # happens, the distribution will not be on PyPI, but the file will be
        # in the object store, and future repeated upload attempts will fail
        # due missing DB entries for this file, and due to our object store
        # disallowing overwrites.
        #
        # Because the file_path always includes the file's hash (that we
        # calculate on upload) we can be assured that any attempt to upload a
        # blob that already exists is a result of this edge case, and we can
        # safely skip the upload.
        if not blob.exists():
            blob.upload_from_filename(file_path)
        else:
            sentry_sdk.capture_message(f"Skipped uploading duplicate file: {file_path}")


@implementer(IFileStorage)
class GCSFileStorage(GenericGCSBlobStorage):
    @classmethod
    @google.api_core.retry.Retry(
        predicate=google.api_core.retry.if_exception_type(
            google.api_core.exceptions.ServiceUnavailable
        )
    )
    def create_service(cls, context, request):
        storage_client = request.find_service(name="gcloud.gcs")
        bucket_name = request.registry.settings["files.bucket"]
        bucket = storage_client.get_bucket(bucket_name)
        prefix = request.registry.settings.get("files.prefix")

        return cls(bucket, prefix=prefix)


@implementer(ISimpleStorage)
class GCSSimpleStorage(GenericGCSBlobStorage):
    @classmethod
    @google.api_core.retry.Retry(
        predicate=google.api_core.retry.if_exception_type(
            google.api_core.exceptions.ServiceUnavailable
        )
    )
    def create_service(cls, context, request):
        storage_client = request.find_service(name="gcloud.gcs")
        bucket_name = request.registry.settings["simple.bucket"]
        bucket = storage_client.get_bucket(bucket_name)
        prefix = request.registry.settings.get("simple.prefix")

        return cls(bucket, prefix=prefix)


@implementer(IProjectService)
class ProjectService:
    def __init__(
        self, session, metrics=None, ratelimiters=None, query_results_cache=None
    ) -> None:
        if ratelimiters is None:
            ratelimiters = {}
        if query_results_cache is None:
            query_results_cache = {}

        self.db = session
        self.ratelimiters = collections.defaultdict(DummyRateLimiter, ratelimiters)
        self._metrics = metrics
        self._query_results_cache = query_results_cache

    def _check_ratelimits(self, request, creator):
        # First we want to check if a single IP is exceeding our rate limiter.
        if request.remote_addr is not None:
            if not self.ratelimiters["project.create.ip"].test(request.remote_addr):
                logger.warning("IP failed project create threshold reached.")
                self._metrics.increment(
                    "warehouse.project.create.ratelimited",
                    tags=["ratelimiter:ip"],
                )
                raise TooManyProjectsCreated(
                    resets_in=self.ratelimiters["project.create.ip"].resets_in(
                        request.remote_addr
                    )
                )

        if not self.ratelimiters["project.create.user"].test(creator.id):
            logger.warning("User failed project create threshold reached.")
            self._metrics.increment(
                "warehouse.project.create.ratelimited",
                tags=["ratelimiter:user"],
            )
            raise TooManyProjectsCreated(
                resets_in=self.ratelimiters["project.create.user"].resets_in(
                    request.remote_addr
                )
            )

    def _hit_ratelimits(self, request, creator):
        self.ratelimiters["project.create.user"].hit(creator.id)
        self.ratelimiters["project.create.ip"].hit(request.remote_addr)

    def check_project_name(self, name: str) -> None:
        """
        Check if a project name is valid and available.

        This method will raise an exception if the project name is invalid or
        unavailable for any reason.
        """
        if not PROJECT_NAME_RE.match(name):
            raise ProjectNameUnavailableInvalidError()

        # Also check for collisions with Python Standard Library modules.
        if canonicalize_name(name) in STDLIB_PROHIBITED:
            raise ProjectNameUnavailableStdlibError()

        if existing_project := self.db.scalars(
            select(Project).where(
                Project.normalized_name == func.normalize_pep426_name(name)
            )
        ).first():
            raise ProjectNameUnavailableExistingError(existing_project)

        if self.db.query(
            exists().where(
                ProhibitedProjectName.name == func.normalize_pep426_name(name)
            )
        ).scalar():
            raise ProjectNameUnavailableProhibitedError()

        if similar_project_name := self.db.scalars(
            select(Project.name).where(
                func.ultranormalize_name(Project.name) == func.ultranormalize_name(name)
            )
        ).first():
            raise ProjectNameUnavailableSimilarError(similar_project_name)

        # Check for typo-squatting.
        cached_corpus = self._query_results_cache.get("top_dependents_corpus")
        if typo_check_match := typo_check_name(
            canonicalize_name(name), corpus=cached_corpus
        ):
            raise ProjectNameUnavailableTypoSquattingError(
                check_name=typo_check_match[0],
                existing_project_name=typo_check_match[1],
            )

        return None

    def create_project(
        self,
        name,
        creator,
        request,
        *,
        creator_is_owner=True,
        ratelimited=True,
        organization_id=None,
    ):
        if ratelimited:
            self._check_ratelimits(request, creator)

        # Check for AdminFlag set by a PyPI Administrator disabling new project
        # registration, reasons for this include Spammers, security
        # vulnerabilities, or just wanting to be lazy and not worry ;)
        if request.flags.enabled(AdminFlagValue.DISALLOW_NEW_PROJECT_REGISTRATION):
            raise HTTPForbidden(
                (
                    "New project registration temporarily disabled. "
                    "See {projecthelp} for more information."
                ).format(projecthelp=request.help_url(_anchor="admin-intervention")),
            ) from None

        # Verify that the project name is both valid and currently available.
        try:
            self.check_project_name(name)
        except ProjectNameUnavailableInvalidError:
            raise HTTPBadRequest(f"The name {name!r} is invalid.")
        except ProjectNameUnavailableExistingError:
            # Found existing project with conflicting name.
            raise HTTPConflict(
                (
                    "The name {name!r} conflicts with an existing project. "
                    "See {projecthelp} for more information."
                ).format(
                    name=name,
                    projecthelp=request.help_url(_anchor="project-name"),
                ),
            ) from None
        except ProjectNameUnavailableProhibitedError:
            raise HTTPBadRequest(
                (
                    "The name {name!r} isn't allowed. "
                    "See {projecthelp} for more information."
                ).format(
                    name=name,
                    projecthelp=request.help_url(_anchor="project-name"),
                ),
            ) from None
        except ProjectNameUnavailableSimilarError:
            raise HTTPBadRequest(
                (
                    "The name {name!r} is too similar to an existing project. "
                    "See {projecthelp} for more information."
                ).format(
                    name=name,
                    projecthelp=request.help_url(_anchor="project-name"),
                ),
            ) from None
        except ProjectNameUnavailableStdlibError:
            raise HTTPBadRequest(
                (
                    "The name {name!r} isn't allowed (conflict with Python "
                    "Standard Library module name). See "
                    "{projecthelp} for more information."
                ).format(
                    name=name,
                    projecthelp=request.help_url(_anchor="project-name"),
                ),
            ) from None
        except ProjectNameUnavailableTypoSquattingError as exc:
            # Don't yet raise an error here, as we want to allow the
            # user to proceed with the project creation. We'll log a warning
            # instead.
            request.log.warning(
                "ProjectNameUnavailableTypoSquattingError",
                check_name=exc.check_name,
                existing_project_name=exc.existing_project_name,
            )
            # Send notification to Admins for review
            notification_service = request.find_service(IAdminNotificationService)

            warehouse_domain = request.registry.settings.get("warehouse.domain")
            new_project_page = request.route_url(
                "packaging.project",
                name=name,
                _host=warehouse_domain,
            )
            new_project_text = (
                f"During `file_upload`, Project Create for "
                f"*<{new_project_page}|{name}>* was detected as a potential "
                f"typo by the `{exc.check_name!r}` check."
            )
            existing_project_page = request.route_url(
                "packaging.project",
                name=exc.existing_project_name,
                _host=warehouse_domain,
            )
            existing_project_text = (
                f"<{existing_project_page}|Existing project: "
                f"{exc.existing_project_name}>"
            )

            webhook_payload = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "TypoSnyper :warning:",
                            "emoji": True,
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": new_project_text,
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": existing_project_text,
                        },
                    },
                    {"type": "divider"},
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "plain_text",
                                "text": "Once reviewed/confirmed, "
                                "react to this message with :white_check_mark:",
                                "emoji": True,
                            }
                        ],
                    },
                ]
            }
            notification_service.send_notification(payload=webhook_payload)

            request.metrics.increment(
                "warehouse.packaging.services.create_project.typo_squatting",
                tags=[f"check_name:{exc.check_name!r}"],
            )
            # and continue with the project creation
            pass

        # The project name is valid: create it and add it
        project = Project(name=name)
        self.db.add(project)
        self.db.flush()  # To get the new ID

        # TODO: This should be handled by some sort of database trigger or a
        #       SQLAlchemy hook or the like instead of doing it inline in this
        #       service.
        self.db.add(
            JournalEntry(
                name=project.name,
                action="create",
                submitted_by=creator,
            )
        )
        project.record_event(
            tag=EventTag.Project.ProjectCreate,
            request=request,
            additional={"created_by": creator.username},
        )

        if organization_id:
            # If an organization ID is provided, we never set the creator to owner
            self.db.add(
                OrganizationProject(
                    organization_id=organization_id, project_id=project.id
                )
            )
        elif creator_is_owner:
            # Mark the creator as the newly created project's owner, if configured.
            self.db.add(Role(user=creator, project=project, role_name="Owner"))
            # TODO: This should be handled by some sort of database trigger or a
            #       SQLAlchemy hook or the like instead of doing it inline in this
            #       service.
            self.db.add(
                JournalEntry(
                    name=project.name,
                    action=f"add Owner {creator.username}",
                    submitted_by=creator,
                )
            )
            project.record_event(
                tag=EventTag.Project.RoleAdd,
                request=request,
                additional={
                    "submitted_by": creator.username,
                    "role_name": "Owner",
                    "target_user": creator.username,
                },
            )

        # Remove all pending publishers not owned by the creator.
        # There might be other pending publishers for the same or similar project
        # name, which we've now invalidated by creating the project. These would
        # be disposed of on use, but we explicitly dispose of them here while
        # also sending emails to their owners.
        stale_pending_publishers = (
            request.db.query(PendingOIDCPublisher)
            .filter(
                func.ultranormalize_name(PendingOIDCPublisher.project_name)
                == func.ultranormalize_name(project.name),
                PendingOIDCPublisher.added_by != creator,
            )
            .all()
        )
        for stale_publisher in stale_pending_publishers:
            send_pending_trusted_publisher_invalidated_email(
                request,
                stale_publisher.added_by,
                project_name=stale_publisher.project_name,
            )
            request.db.delete(stale_publisher)

        if ratelimited:
            self._hit_ratelimits(request, creator)
        return project


def project_service_factory(context, request):
    metrics = request.find_service(IMetricsService, context=None)
    ratelimiters = {
        "project.create.user": request.find_service(
            IRateLimiter, name="project.create.user", context=None
        ),
        "project.create.ip": request.find_service(
            IRateLimiter, name="project.create.ip", context=None
        ),
    }
    query_results_cache = request.find_service(IQueryResultsCache)
    return ProjectService(
        request.db,
        metrics=metrics,
        ratelimiters=ratelimiters,
        query_results_cache=query_results_cache,
    )
