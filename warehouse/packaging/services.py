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

import os.path
import shutil
import warnings

import botocore.exceptions
import google.api_core.exceptions
import google.api_core.retry
import sentry_sdk

from zope.interface import implementer

from warehouse.events.tags import EventTag
from warehouse.packaging.interfaces import (
    IDocsStorage,
    IFileStorage,
    IProjectService,
    ISimpleStorage,
)
from warehouse.packaging.models import JournalEntry, Project, Role


class InsecureStorageWarning(UserWarning):
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

    def store(self, path, file_path, *, meta=None):
        destination = os.path.join(self.base, path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as dest_fp:
            with open(file_path, "rb") as src_fp:
                dest_fp.write(src_fp.read())


@implementer(IFileStorage)
class LocalFileStorage(GenericLocalBlobStorage):
    @classmethod
    def create_service(cls, context, request):
        return cls(request.registry.settings["files.path"])


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
    def __init__(self, bucket, *, prefix=None):
        self.bucket = bucket
        self.prefix = prefix

    def _get_path(self, path):
        # If we have a prefix, then prepend it to our path. This will let us
        # store items inside of a sub directory without exposing that to end
        # users.
        if self.prefix:
            path = self.prefix + path

        return path


class GenericS3BlobStorage(GenericBlobStorage):
    def get(self, path):
        # Note: this is not actually used in production, instead our CDN is
        # configured to connect directly to our storage bucket. See:
        # https://github.com/python/pypi-infra/blob/master/terraform/file-hosting/vcl/main.vcl
        try:
            return self.bucket.Object(self._get_path(path)).get()["Body"]
        except botocore.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchKey":
                raise
            raise FileNotFoundError(f"No such key: {path!r}") from None

    def store(self, path, file_path, *, meta=None):
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
    def get(self, path):
        # Note: this is not actually used in production, instead our CDN is
        # configured to connect directly to our storage bucket. See:
        # https://github.com/python/pypi-infra/blob/master/terraform/file-hosting/vcl/main.vcl
        raise NotImplementedError

    @google.api_core.retry.Retry(
        predicate=google.api_core.retry.if_exception_type(
            google.api_core.exceptions.ServiceUnavailable
        )
    )
    def store(self, path, file_path, *, meta=None):
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
    def __init__(self, session, remote_addr) -> None:
        self.db = session
        self.remote_addr = remote_addr

    def create_project(self, name, owner):
        project = Project(name=name)
        self.db.add(project)

        # TODO: This should be handled by some sort of database trigger or a
        #       SQLAlchemy hook or the like instead of doing it inline in this
        #       service.
        self.db.add(
            JournalEntry(
                name=project.name,
                action="create",
                submitted_by=owner,
                submitted_from=self.remote_addr,
            )
        )
        project.record_event(
            tag=EventTag.Project.ProjectCreate,
            ip_address=self.remote_addr,
            additional={"created_by": owner.username},
        )

        # Then we'll add a role setting the current user as the "Owner" of the
        # project.
        self.db.add(Role(user=owner, project=project, role_name="Owner"))
        # TODO: This should be handled by some sort of database trigger or a
        #       SQLAlchemy hook or the like instead of doing it inline in this
        #       service.
        self.db.add(
            JournalEntry(
                name=project.name,
                action=f"add Owner {owner.username}",
                submitted_by=owner,
                submitted_from=self.remote_addr,
            )
        )
        project.record_event(
            tag=EventTag.Project.RoleAdd,
            ip_address=self.remote_addr,
            additional={
                "submitted_by": owner.username,
                "role_name": "Owner",
                "target_user": owner.username,
            },
        )

        return project


def project_service_factory(context, request):
    return ProjectService(request.db, request.remote_addr)
