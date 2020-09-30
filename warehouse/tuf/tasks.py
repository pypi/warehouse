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
from warehouse.tuf.constants import HASH_ALGORITHM, TUF_REPO_LOCK, Role
from warehouse.tuf.interfaces import IKeyService, IStorageService


@task(bind=True, ignore_result=True, acks_late=True)
def bump_snapshot(task, request):
    """
    Re-signs the TUF snapshot role, incrementing its version and renewing its
    expiration period.

    Bumping the snapshot transitively bumps the timestamp role.
    """
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])

    with r.lock(TUF_REPO_LOCK):
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
        # 4. We call `utils.bump_metadata()` and `Snapshot.sign()` to bump
        #    and re-sign the current snapshot.
        # 5. We call `Snapshot.to_json_file()` with `{VERSION + 1}.snapshot.json`,
        #    where `{VERSION + 1}` is the incremented snapshot version.
        # 6. We call `Timestamp.update()` on the loaded timestamp, giving it the
        #    incremented snapshot version as well as the serialized length and
        #    BLAKE2B hash of the serialized form.
        # 7. We call `utils.bump_metadata()` and `Timestamp.sign()` to bump
        #    and re-sign the current timestamp.
        # 8. We call `Timestamp.to_json_file()`, writing to `timestamp.json`.
        #
        # Each of the steps is labeled below for clarity.

        # 1. Service retrieval.
        storage_service = request.find_service(IStorageService)
        key_service = request.find_service(IKeyService)

        storage_backend = storage_service.get_backend()

        # 2. Timestamp retrieval and loading.
        timestamp = metadata.Timestamp.from_json_file("timestamp.json", storage_backend)

        # 3. Snapshot retrieval and loading.
        snapshot = utils.find_snapshot(timestamp, storage_backend)

        # 4. Snapshot bumping and versioning.
        utils.bump_metadata(
            snapshot,
            timedelta(seconds=request.registry.settings["tuf.snapshot.expiry"]),
        )
        for key in key_service.privkeys_for_role(Role.SNAPSHOT.value):
            snapshot.sign(key)

        # 5. Writing the updated snapshot back to the repository.
        snapshot_filename = f"{snapshot.version}.snapshot.json"
        snapshot.to_json_file(snapshot_filename, storage_backend)

        # 6. Timestamp updating.
        timestamp.update(
            snapshot.version,
            len(snapshot.to_json().encode()),
            get_file_hashes(
                snapshot_filename,
                hash_algorithms=[HASH_ALGORITHM],
                storage_backend=storage_backend,
            ),
        )

        # 7. Timestamp bumping.
        utils.bump_metadata(
            timestamp,
            timedelta(seconds=request.registry.settings["tuf.timestamp.expiry"]),
        )
        for key in key_service.privkeys_for_role(Role.TIMESTAMP.value):
            timestamp.sign(key)

        # 8. Writing the updated timestamp back to the repository.
        timestamp.to_json_file("timestamp.json", storage_backend)


@task(bind=True, ignore_result=True, acks_late=True)
def bump_bin_ns(task, request):
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])

    with r.lock(TUF_REPO_LOCK):
        # Bumping all of the delegated bin roles in the TUF repository involves
        # the following steps:
        # 1. Grab key and storage services.
        # 2. Fetch timestamp.
        # 3. Fetch snapshot using timestamp.
        # 4. For each delegated target in the snapshot, fetch its current version,
        #    bump, re-sign, and write back to the repo. Update the snapshot to
        #    match the bumped version.
        # 5. Bump and re-sign the snapshot.
        # 6. Write the snapshot back.
        # 7. Bump and re-sign the timestamp.
        # 8. Write the timestamp back.

        # 1. Service retrieval.
        storage_service = request.find_service(IStorageService)
        key_service = request.find_service(IKeyService)

        storage_backend = storage_service.get_backend()

        # 2. Timestamp retrieval and loading.
        timestamp = metadata.Timestamp.from_json_file("timestamp.json", storage_backend)

        # 3. Snapshot retrieval and loading.
        snapshot = utils.find_snapshot(timestamp, storage_backend)

        # Target iteration: skip the top-level targets role.
        for role_name, role_info in snapshot.meta.items():
            if role_name == "targets.json":
                continue

            role_version = role_info["version"]
            delegated_bin_filename = f"{role_version}.{role_name}"

            # Load the delegated bin.
            delegated_bin = metadata.Targets.from_json_file(
                delegated_bin_filename, storage_backend
            )

            # Bump and sign the delegated bin.
            utils.bump_metadata(
                delegated_bin,
                timedelta(seconds=request.registry.settings["tuf.bin-n.expiry"]),
            )

            for key in key_service.privkeys_for_role(Role.BIN_N.value):
                delegated_bin.sign(key)

            # Write-back.
            delegated_bin.to_json_file(delegated_bin_filename, storage_backend)

            # Update the snapshot with this updated target's version.
            # TODO: Ideally we'd use snapshot.update here, but that takes
            # the role name without .json on the end. But role_name here
            # has that suffix. Annoying.
            snapshot.meta[role_name]["version"] = delegated_bin.version

        # Bump and sign the snapshot.
        utils.bump_metadata(
            snapshot,
            timedelta(seconds=request.registry.settings["tuf.snapshot.expiry"]),
        )

        for key in key_service.privkeys_for_role(Role.SNAPSHOT.value):
            snapshot.sign(key)

        # Write-back.
        snapshot_filename = f"{snapshot.version}.snapshot.json"
        snapshot.to_json_file(snapshot_filename, storage_backend)


@task(bind=True, ignore_result=True, acks_late=True)
def add_target(task, request, filepath, fileinfo):
    r = redis.StrictRedis.from_url(request.registry.settings["celery.scheduler_url"])

    with r.lock(TUF_REPO_LOCK):
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
        #     Then, we fetch `{VERSION}.{BIN}.json` and load it using the `Targets`
        #     model provided by the TUF API.
        # 5.  We update the delegated bin, bumping its version, expiration, and
        #     adding our new target to it.
        # 6.  We call `Targets.sign()` on the loaded bin, giving it the bin-n
        #     signing key from our key service.
        # 7.  We call `Targets.to_json_file()` with `{VERSION + 1}.{BIN}.json`
        #     as the filepath, where `{VERSION + 1}` is the incremented version
        #     of the previous delegated bin version.
        # 8.  We update the snapshot, bumping its version, expiration, and giving
        #     it our new delegated bin version.
        # 9.  We call `Snapshot.sign()` on the loaded snapshot, giving it the
        #     snapshot signing key from our key service.
        # 10. We call `Snapshot.to_json_file()` with `{VERSION + 1}.snapshot.json`,
        #     where `{VERSION + 1}` is the incremented version of the previous
        #     snapshot version.
        # 11. We update the timestamp, bumping its version, expiration, and giving
        #     it our new snapshot version and integrity information.
        # 12. We call `Timestamp.sign()` on the loaded timestamp, giving it the
        #     timestamp signing key from our key service.
        # 13. We call `Timestamp.to_json_file()`, writing to `timestamp.json`.
        #
        # Each of the steps is labeled below for clarity.

        # 1. Service retrieval.
        storage_service = request.find_service(IStorageService)
        key_service = request.find_service(IKeyService)

        storage_backend = storage_service.get_backend()

        # 2. Timestamp retrieval and loading.
        timestamp = metadata.Timestamp.from_json_file("timestamp.json", storage_backend)

        # 3. Snapshot retrieval and loading.
        snapshot = utils.find_snapshot(timestamp, storage_backend)

        # 4. Delegated bin retrieval and loading.
        delegated_bin_name, delegated_bin = utils.find_delegated_bin(
            filepath, snapshot, storage_backend
        )

        # 5. Updating the delegated bin.
        utils.bump_metadata(
            delegated_bin,
            timedelta(seconds=request.registry.settings["tuf.bin-n.expiry"]),
        )
        delegated_bin.update(filepath, fileinfo)

        # 6. Signing the updated delegated bin metadata.
        for key in key_service.privkeys_for_role(Role.BIN_N.value):
            delegated_bin.sign(key)

        # 7. Writing the updated delegated bin back to the TUF repository.
        delegated_bin.to_json_file(
            f"{delegated_bin.version}.{delegated_bin_name}.json", storage_backend
        )

        # 8. Updating the snapshot.
        # TODO(ww): Fill in length and hashes?
        utils.bump_metadata(
            snapshot,
            timedelta(seconds=request.registry.settings["tuf.snapshot.expiry"]),
        )
        snapshot.update(f"{delegated_bin_name}.json", delegated_bin.version)

        # 9. Signing the updated snapshot metadata.
        for key in key_service.privkeys_for_role(Role.SNAPSHOT.value):
            snapshot.sign(key)

        # 10. Writing the updated snapshot back to the TUF repository.
        snapshot_filename = f"{snapshot.version}.snapshot.json"
        snapshot.to_json_file(
            snapshot_filename,
            storage_backend,
        )

        # 11. Updating the timestamp.
        # NOTE(ww): Calling get_file_hashes here causes us to round-trip
        # through the object store just to compute our snapshot's hash.
        # Maybe add a function to securesystemslib that does the digest
        # calculation on a string/bytes.
        utils.bump_metadata(
            timestamp,
            timedelta(seconds=request.registry.settings["tuf.timestamp.expiry"]),
        )
        timestamp.update(
            snapshot.version,
            len(snapshot.to_json().encode()),
            get_file_hashes(
                snapshot_filename,
                hash_algorithms=[HASH_ALGORITHM],
                storage_backend=storage_backend,
            ),
        )

        # 12. Signing the updated timestamp metadata.
        for key in key_service.privkeys_for_role(Role.TIMESTAMP.value):
            timestamp.sign(key)

        # 13. Writing the updated timestamp back to the TUF repository.
        timestamp.to_json_file("timestamp.json", storage_backend)
