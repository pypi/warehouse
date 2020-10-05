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

import os

from contextlib import contextmanager
from io import BytesIO

import tuf.formats
import tuf.repository_lib

from google.cloud.exceptions import GoogleCloudError, NotFound
from securesystemslib.exceptions import StorageError
from securesystemslib.storage import FilesystemBackend, StorageBackendInterface
from tuf.api import metadata

from warehouse.tuf.constants import BIN_N_COUNT


def make_fileinfo(file, custom=None):
    """
    Given a warehouse.packaging.models.File, create a TUF-compliant
    "fileinfo" dictionary suitable for addition to a delegated bin.

    The optional "custom" kwarg can be used to supply additional custom
    metadata (e.g., metadata for indicating backsigning).
    """
    hashes = {"blake2b": file.blake2_256_digest}
    fileinfo = tuf.formats.make_targets_fileinfo(file.size, hashes, custom=custom)

    return fileinfo


def bump_metadata(metadata, delta):
    """
    Given a tuf.api.metadata.Signed, bump its version and expiration (with the given
    timedelta).
    """
    metadata.bump_version()
    metadata.bump_expiration(delta=delta)


def find_snapshot(timestamp, storage_backend):
    """
    Given a tuf.api.metadata.Timestamp model, return the Snapshot model
    for the consistent snapshot that it references.
    """
    snapshot_version = timestamp.meta["snapshot.json"]["version"]

    return metadata.Snapshot.from_json_file(
        f"{snapshot_version}.snapshot.json", storage_backend
    )


def find_delegated_bin(filepath, snapshot, storage_backend):
    """
    Given a new target filepath and a tuf.api.metadata.Snapshot model,
    return a tuple of the bin name and tup.api.metadata.Targets for the consistent
    delegated targets bin that the target belongs in.
    """

    # TODO: This probably isn't using the right hash function.
    filepath_hash = tuf.repository_lib.get_target_hash(filepath)
    bin_name = tuf.repository_lib(filepath_hash, BIN_N_COUNT)
    bin_version = snapshot.meta[f"{bin_name}.json"]["version"]

    return bin_name, metadata.Targets.from_json_file(
        f"{bin_version}.{bin_name}.json", storage_backend
    )


class LocalBackend(StorageBackendInterface):
    def __init__(self, request):
        self._filesystem_backend = FilesystemBackend()
        self._repo_path = request.registry.settings["tuf.repo.path"]

    @contextmanager
    def get(self, filepath):
        yield from self._filesystem_backend.get(os.path.join(self._repo_path, filepath))

    def put(self, fileobj, filepath):
        return self._filesystem_backend.put(
            fileobj, os.path.join(self._repo_path, filepath)
        )

    def remove(self, filepath):
        return self._filesystem_backend.remove(os.path.join(self._repo_path, filepath))

    def getsize(self, filepath):
        return self._filesystem_backend.getsize(os.path.join(self._repo_path, filepath))

    def create_folder(self, filepath):
        return self._filesystem_backend.create_folder(
            os.path.join(self._repo_path, filepath)
        )

    def list_folder(self, filepath):
        return self._filesystem_backend.list_folder(
            os.path.join(self._repo_path, filepath)
        )


class GCSBackend(StorageBackendInterface):
    def __init__(self, request):
        self._client = request.find_service(name="gcloud.gcs")
        # NOTE: This needs to be created.
        self._bucket = self._client.get_bucket(request.registry.settings["tuf.bucket"])

    @contextmanager
    def get(self, filepath):
        try:
            contents = self._bucket.blob(filepath).download_as_string()
            yield BytesIO(contents)
        except NotFound as e:
            raise StorageError(f"{filepath} not found")

    def put(self, fileobj, filepath):
        try:
            blob = self._bucket.blob(filepath)
            # NOTE(ww): rewind=True reflects the behavior of the securesystemslib
            # implementation of StorageBackendInterface, which seeks to the file start.
            # I'm not sure it's actually required.
            blob.upload_from_file(fileobj, rewind=True)
        except GoogleCloudError:
            # TODO: expose details of the underlying error in the message here?
            raise StorageError(f"couldn't store to {filepath}")

    def remove(self, filepath):
        try:
            self._bucket.blob(filepath).delete()
        except NotFound:
            raise StorageError(f"{filepath} not found")

    def getsize(self, filepath):
        blob = self._bucket.get_blob(filepath)

        if blob is None:
            raise StorageError(f"{filepath} not found")

        return blob.size

    def create_folder(self, filepath):
        if not filepath:
            return

        if not filepath.endswith("/"):
            filepath = f"{filepath}/"

        try:
            blob = self._bucket.blob(filepath)
            blob.upload_from_string(b"")
        except GoogleCloudError as e:
            raise StorageError(f"couldn't create folder: {filepath}")

    def list_folder(self, filepath):
        if not filepath.endswith("/"):
            filepath = f"{filepath}/"

        # NOTE: The `nextPageToken` appears to be required due to an implementation detail leak.
        # See https://github.com/googleapis/google-cloud-python/issues/7875
        blobs = self._client.list_blobs(
            self._bucket, prefix=filepath, fields="items(name),nextPageToken"
        )
        return [blob.name for blob in blobs]
