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

from contextlib import contextmanager
from io import BytesIO

import tuf.formats
import tuf.repository_tool

from google.cloud.exceptions import GoogleCloudError, NotFound
from securesystemslib.exceptions import StorageError
from securesystemslib.storage import StorageBackendInterface


def make_fileinfo(file, custom=None):
    """
    Given a warehouse.packaging.models.File, create a TUF-compliant
    "fileinfo" dictionary suitable for addition to a delegated bin.

    The optional "custom" kwarg can be used to supply additional custom
    metadata (e.g., metadata for indicating backsigning).
    """
    hashes = {"blake2b": file.blake2_256_digest}
    fileinfo = tuf.formats.make_fileinfo(file.size, hashes, custom=custom)

    return fileinfo


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


class RepoLock:
    """
    Supplies a blocking lock for TUF repository operations.
    """

    def __init__(self, redis_client):
        self.lock = redis_client.lock("tuf-repo")

    def __enter__(self):
        self.lock.acquire()
        return self

    def __exit__(self, *_exc):
        self.lock.release()
