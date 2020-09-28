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

from datetime import timedelta

import redis

from securesystemslib.util import get_file_hashes
from tuf.api import metadata

from warehouse.tasks import task
from warehouse.tuf import utils
from warehouse.tuf.constants import HASH_ALGORITHM
from warehouse.tuf.interfaces import IKeyService, IRepositoryService, IStorageService


@task(bind=True, ignore_result=True, acks_late=True)
def bump_snapshot(task, request):
    """
    Re-signs the TUF snapshot role, incrementing its version and renewing its
    expiration period.

    Bumping the snapshot transitively bumps the timestamp role.
    """
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])

    with r.lock("tuf-repo"):
        # Bumping the snapshot role involves the following steps:
        # 1. First, we grab our key and storage services. We'll use the former
        #    for signing operations, and the latter to read and write individual
        #    metadata files to and from the repository without loading the entire
        #    repo.
        # 2. Using our storage service, we fetch the timestamp metadata, which
        #    is always at `timestamp.json`. We load it using the `Timestamp` model
        #    provided by the TUF API.
        # 3. Using the snapshot version stored in the current `Timestamp`, we fetch
        #    `{VERSION}.snapshot.json` and load it using the `Snapshot` model
        #    provided by the TUF API.
        # 4. We call `Snapshot.bump_version()` and `Snapshot.sign()` to bump
        #    and re-sign the current snapshot.
        # 5. We call `Snapshot.to_json_file()` with `{VERSION + 1}.snapshot.json`,
        #    where `{VERSION + 1}` is the incremented snapshot version.
        # 6. We call `Timestamp.update()` on the loaded timestamp, giving it the
        #    incremented snapshot version as well as the serialized length and
        #    BLAKE2B hash of the serialized form.
        # 7. We call `Timestamp.bump_version()` and `Timestamp.sign()` to bump
        #    and re-sign the current timestamp.
        # 8. We call `Timestamp.to_json_file()`, writing to `timestamp.json`.
        #
        # Each of the steps is labeled below for clarity.0

        # 1. Service retrieval.
        storage_service = request.find_service(IStorageService)
        key_service = request.find_service(IKeyService)

        storage_backend = storage_service.get_backend()

        # 2. Timestamp retrieval and loading.
        timestamp = metadata.Timestamp.from_json_file("timestamp.json", storage_backend)

        # 3. Snapshot retrieval and loading.
        snapshot_version, snapshot_filename = utils.find_snapshot(timestamp)
        snapshot = metadata.Snapshot.from_json_file(snapshot_filename, storage_backend)

        # 4. Snapshot bumping and versioning.
        snapshot_version += 1
        snapshot.bump_version()
        snapshot.bump_expiration(
            delta=timedelta(seconds=request.registry.settings["tuf.snapshot.expiry"])
        )
        for key in key_service.privkeys_for_role("snapshot"):
            snapshot.sign(key)

        # 5. Writing the updated snapshot back to the repository.
        snapshot_filename = f"{snapshot_version}.snapshot.json"
        snapshot.to_json_file(snapshot_filename, storage_backend)

        # 6. Timestamp updating.
        timestamp.update(
            snapshot_version,
            len(snapshot.to_json().encode()),
            get_file_hashes(
                snapshot_filename,
                hash_algorithms=[HASH_ALGORITHM],
                storage_backend=storage_backend,
            ),
        )

        # 7. Timestamp bumping.
        timestamp.bump_version()
        timestamp.bump_expiration(
            delta=timedelta(seconds=request.registry.settings["tuf.timestamp.expiry"])
        )

        # 8. Writing the updated timestamp back to the repository.
        timestamp.to_json_file("timestamp.json", storage_backend)


@task(bind=True, ignore_result=True, acks_late=True)
def bump_bin_ns(task, request):
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])

    with r.lock("tuf-repo"):
        pass


@task(bind=True, ignore_result=True, acks_late=True)
def add_target(task, request, filepath, fileinfo):
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])

    with r.lock("tuf-repo"):
        # Adding a target to the TUF repository involves the following steps:
        # 1.  First, we grab our key and storage services. We'll use the former
        #     for signing operations, and the latter to read and write individual
        #     metadata files to and from the repository without loading the entire
        #     repo.
        # 2.  Using our storage service, we fetch the timestamp metadata, which
        #     is always at `timestamp.json`. We load it using the `Timestamp` model
        #     provided by the TUF API.
        # 3.  Using the snapshot version stored in the current `Timestamp`, we fetch
        #     `{VERSION}.snapshot.json` and load it using the `Snapshot` model
        #     provided by the TUF API.
        # 4.  Using the target's name (`filepath`), we determine the name of the
        #     delegated bin that it'll end up in. We use that delegated bin name to
        #     index into the `Snapshot` model and get the current version for that bin.
        # 5.  Using the delegated bin name and version determined in #4, we fetch
        #     `{VERSION}.{BIN}.json` and load it using the `Targets` model provided
        #     by the TUF API.
        # 6.  We call `Targets.update()` on the loaded bin, passing it the
        #     `filename` and `fileinfo` for the target that we're adding.
        # 7.  We call `Targets.sign()` on the loaded bin, giving it the bin-n
        #     signing key from our key service.
        # 8.  We call `Targets.to_json_file()` with `{VERSION + 1}.{BIN}.json`
        #     as the filepath, where `{VERSION + 1}` is the incremented version
        #     of the previous delegated bin version.
        # 9.  We call `Snapshot.update()` on the loaded snapshot, passing it
        #     the name of the delegated bin and its new version (`{VERSION + 1}`).
        # 10. We call `Snapshot.sign()` on the loaded snapshot, giving it the
        #     snapshot signing key from our key service.
        # 11. We call `Snapshot.to_json_file()` with `{VERSION + 1}.snapshot.json`,
        #     where `{VERSION + 1}` is the incremented version of the previous
        #     snapshot version.
        # 12. We call `Timestamp.update()` on the loaded timestamp, passing it
        #     the new snapshot version (`{VERSION + 1}`) as well as the serialized
        #     length and BLAKE2B hash of the serialized form.
        # 13. We call `Timestamp.sign()` on the loaded timestamp, giving it the
        #     timestamp signing key from our key service.
        # 14. We call `Timestamp.to_json_file()`, writing to `timestamp.json`.
        #
        # Each of the steps is labeled below for clarity.

        # 1. Service retrieval.
        storage_service = request.find_service(IStorageService)
        key_service = request.find_service(IKeyService)

        storage_backend = storage_service.get_backend()

        # 2. Timestamp retrieval and loading.
        timestamp = metadata.Timestamp.from_json_file("timestamp.json", storage_backend)

        # 3. Snapshot retrieval and loading.
        snapshot_version, snapshot_filename = utils.find_snapshot(timestamp)
        snapshot = metadata.Snapshot.from_json_file(snapshot_filename, storage_backend)

        # 4. Delegated bin determination.
        (
            delegated_bin_version,
            delegated_bin_name,
            delegated_bin_filename,
        ) = utils.find_delegated_bin(filepath, snapshot)

        # 5. Delegated bin retrieval and loading.
        delegated_bin = metadata.Targets.from_json_file(
            delegated_bin_filename, storage_backend
        )

        # 6. Adding the target to the delegated bin.
        # XXX(ww): This doesn't bump the metadata envelope's version or expiration.
        delegated_bin.update(filepath, fileinfo)

        # 7. Signing the updated delegated bin metadata.
        for key in key_service.privkeys_for_role("bin-n"):
            delegated_bin.sign(key)

        # 8. Writing the updated delegated bin back to the TUF repository.
        delegated_bin_version += 1
        delegated_bin.to_json_file(
            f"{delegated_bin_version}.{delegated_bin_name}.json", storage_backend
        )

        # 9. Updating the snapshot to reference our new delegated bin version.
        # TODO(ww): Fill in length and hashes?
        # XXX(ww): This doesn't bump the metadata envelope's version or expiration.
        snapshot.update(f"{delegated_bin_name}.json", delegated_bin_version)

        # 10. Signing the updated snapshot metadata.
        for key in key_service.privkeys_for_role("snapshot"):
            snapshot.sign(key)

        # 11. Writing the updated snapshot back to the TUF repository.
        snapshot_version += 1
        snapshot_filename = f"{snapshot_version}.snapshot.json"
        snapshot.to_json_file(
            snapshot_filename,
            storage_backend,
        )

        # 12. Updating the timestamp to reference our new snapshot version.
        # NOTE(ww): Calling get_file_hashes here causes us to round-trip
        # through the object store just to compute our snapshot's hash.
        # Maybe add a function to securesystemslib that does the digest
        # calculation on a string/bytes.
        # XXX(ww): This doesn't bump the metadata envelope's version or expiration.
        timestamp.update(
            snapshot_version,
            len(snapshot.to_json().encode()),
            get_file_hashes(
                snapshot_filename,
                hash_algorithms=[HASH_ALGORITHM],
                storage_backend=storage_backend,
            ),
        )

        # 13. Signing the updated timestamp metadata.
        for key in key_service.privkeys_for_role("timestamp"):
            snapshot.sign(key)

        # 14. Writing the updated timestamp back to the TUF repository.
        timestamp.to_json_file("timestamp.json", storage_backend)
