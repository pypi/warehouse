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


import datetime
import glob
import os.path
import shutil
import warnings

from contextlib import contextmanager

from securesystemslib.exceptions import StorageError  # type: ignore
from securesystemslib.interface import (  # type: ignore
    import_ed25519_privatekey_from_file,
)
from zope.interface import implementer

from warehouse.config import Environment
from warehouse.tuf.constants import BIN_N_COUNT, Role
from warehouse.tuf.hash_bins import HashBins
from warehouse.tuf.interfaces import IKeyService, IRepositoryService, IStorageService
from warehouse.tuf.repository import (
    TOP_LEVEL_ROLE_NAMES,
    MetadataRepository,
    RolesPayload,
    TargetFile,
)


class InsecureKeyWarning(UserWarning):
    pass


@implementer(IKeyService)
class LocalKeyService:
    """
    A service to read private TUF role keys as local files for development.

    NOTE: Do not use in production!
    """

    def __init__(self, key_path, request):
        warnings.warn(
            "LocalKeyService is intended only for use in development, you "
            "should not use it in production to avoid unnecessary key exposure.",
            InsecureKeyWarning,
        )

        self._key_path = key_path
        self._request = request

    @classmethod
    def create_service(cls, context, request):
        return cls(request.registry.settings["tuf.key.path"], request)

    def get(self, rolename):
        """
        Returns Key objects for passed TUF role name from configured TUF key path.
        """
        privkey_path = os.path.join(self._key_path, "tufkeys", f"{rolename}*")
        role_keys = glob.glob(privkey_path)
        keys_sslib = [
            import_ed25519_privatekey_from_file(
                key, self._request.registry.settings[f"tuf.{rolename}.secret"]
            )
            for key in role_keys
            if "pub" not in key
        ]

        return keys_sslib


@implementer(IStorageService)
class LocalStorageService:
    """
    A storage service with methods to read and write TUF role metadata as local files.
    """

    def __init__(self, repo_path):
        self._repo_path = repo_path

    @classmethod
    def create_service(cls, context, request):
        return cls(
            request.registry.settings["tuf.repo.path"],
        )

    @contextmanager
    def get(self, role, version=None):
        """
        Yields TUF role metadata file object for the passed role name, from the
        configured TUF repo path, optionally at the passed version (latest if None).
        """

        if role == Role.TIMESTAMP.value:
            filename = os.path.join(self._repo_path, f"{role}.json")
        else:
            if version is None:
                filenames = glob.glob(os.path.join(self._repo_path, f"*.{role}.json"))
                versions = [
                    int(name.split("/")[-1].split(".", 1)[0]) for name in filenames
                ]
                try:
                    version = max(versions)
                except ValueError:
                    version = 1

            filename = os.path.join(self._repo_path, f"{version}.{role}.json")

        file_object = None
        try:
            file_object = open(filename, "rb")
            yield file_object
        except OSError:
            raise StorageError(f"Can't open {filename}")
        finally:
            if file_object is not None:
                file_object.close()

    def put(self, file_object, filename):
        """
        Writes passed file object to configured TUF repo path using the passed filename.
        """
        file_path = os.path.join(self._repo_path, filename)
        if not file_object.closed:
            file_object.seek(0)

        try:
            with open(file_path, "wb") as destination_file:
                shutil.copyfileobj(file_object, destination_file)
                destination_file.flush()
                os.fsync(destination_file.fileno())
        except OSError:
            raise StorageError(f"Can't write file {filename}")

    def store(self, file_object, filename):
        self.put(file_object, filename)


@implementer(IRepositoryService)
class RepositoryService:
    """
    A repository service to create and maintain TUF role metadata.
    """

    def __init__(self, storage_service, key_service, request):
        self._storage_backend = storage_service
        self._key_storage_backend = key_service
        self._request = request

    @classmethod
    def create_service(cls, context, request):
        """
        Creates a new repository service object configuring services to read and write
        TUF role metadata (``IStorageService``) and to read private keys
        (``IKeyService``).
        """
        storage_service = request.find_service(IStorageService)
        key_service = request.find_service(IKeyService)
        return cls(storage_service, key_service, request)

    def _get_hash_bins(self):
        """
        Returns a 'hash bin delegation' management object.
        """
        if self._request.registry.settings["warehouse.env"] == Environment.development:
            number_of_bins = 32
        else:
            number_of_bins = BIN_N_COUNT

        return HashBins(number_of_bins)

    def _set_expiration_for_role(self, role_name):
        """
        Returns a metadata expiration date (now + role-specific interval).
        """
        # In a development environment metadata expires less frequently  so that
        # developers don't have to continually re-initialize it.
        if self._request.registry.settings["warehouse.env"] == Environment.development:
            return datetime.datetime.now().replace(microsecond=0) + datetime.timedelta(
                seconds=self._request.registry.settings[
                    "tuf.development_metadata_expiry"
                ]
            )
        else:
            return datetime.datetime.now().replace(microsecond=0) + datetime.timedelta(
                seconds=self._request.registry.settings[f"tuf.{role_name}.expiry"]
            )

    def init_repository(self):
        """
        Creates TUF top-level role metadata (root, targets, snapshot, timestamp).

        The metadata is populated with configured expiration times, signature thresholds
        and verification keys, and signed and persisted using the configured key and
        storage services.

        FIXME: In production 'root' and 'targets' roles require offline singing keys,
        which may not be available at the time of initializing this metadata.
        """
        metadata_repository = MetadataRepository(
            self._storage_backend, self._key_storage_backend
        )

        if metadata_repository.is_initialized:
            raise FileExistsError("TUF Metadata Repository files already exists.")

        top_roles_payload = dict()
        for role in TOP_LEVEL_ROLE_NAMES:
            top_roles_payload[role] = RolesPayload(
                expiration=self._set_expiration_for_role(role),
                threshold=self._request.registry.settings[f"tuf.{role}.threshold"],
                keys=self._key_storage_backend.get(role),
            )

        metadata_repository.initialize(top_roles_payload, True)

    def init_targets_delegation(self):
        """
        Creates TUF metadata for hash bin delegated targets roles (bins, bin-n).

        Metadata is created for one 'bins' role and a configured number of 'bin-n'
        roles. It is populated with configured expiration times, signature thresholds
        and verification keys, and signed and persisted using the configured key and
        storage services.

        FIXME: In production the 'bins' role requires an offline singing key, which may
        not be available at the time of initializing this metadata.
        """
        hash_bins = self._get_hash_bins()
        metadata_repository = MetadataRepository(
            self._storage_backend, self._key_storage_backend
        )

        # Top-level 'targets' role delegates trust for all target files to 'bins' role.
        delegate_roles_payload = dict()
        delegate_roles_payload["targets"] = list()
        delegate_roles_payload["targets"].append(
            RolesPayload(
                expiration=self._set_expiration_for_role(Role.BINS.value),
                threshold=self._request.registry.settings[
                    f"tuf.{Role.BINS.value}.threshold"
                ],
                keys=self._key_storage_backend.get(Role.BINS.value),
                delegation_role=Role.BINS.value,
                paths=["*/*", "*/*/*/*"],
            )
        )
        # The 'bins' role delegates trust for target files to 'bin-n' roles based on
        # target file path hash prefixes.
        delegate_roles_payload[Role.BINS.value] = list()
        for bin_n_name, bin_n_hash_prefixes in hash_bins.generate():
            delegate_roles_payload[Role.BINS.value].append(
                RolesPayload(
                    expiration=self._set_expiration_for_role(Role.BIN_N.value),
                    threshold=self._request.registry.settings[
                        f"tuf.{Role.BIN_N.value}.threshold"
                    ],
                    keys=self._key_storage_backend.get(Role.BIN_N.value),
                    delegation_role=bin_n_name,
                    path_hash_prefixes=bin_n_hash_prefixes,
                )
            )

        snapshot_metadata = metadata_repository.delegate_targets_roles(
            delegate_roles_payload,
        )
        self.bump_snapshot(snapshot_metadata)

    def bump_snapshot(self, snapshot_metadata=None):
        """
        Bumps version and expiration date of TUF 'snapshot' role metadata.

        The version number is incremented by one, the expiration date renewed using a
        configured expiration interval, and the metadata is signed and persisted using
        the configured key and storage services.

        Bumping 'snapshot' transitively bumps the 'timestamp' role.
        """
        metadata_repository = MetadataRepository(
            self._storage_backend, self._key_storage_backend
        )

        if snapshot_metadata is None:
            snapshot_metadata = metadata_repository.load_role(Role.SNAPSHOT.value)

        snapshot_metadata = metadata_repository.snapshot_bump_version(
            snapshot_expires=self._set_expiration_for_role(Role.SNAPSHOT.value),
            snapshot_metadata=snapshot_metadata,
            store=True,
        )

        metadata_repository.timestamp_bump_version(
            snapshot_version=snapshot_metadata.signed.version,
            timestamp_expires=self._set_expiration_for_role(Role.TIMESTAMP.value),
            store=True,
        )

    def bump_bin_n_roles(self):
        """
        Bumps version and expiration date of 'bin-n' role metadata (multiple).

        The version numbers are incremented by one, the expiration dates are renewed
        using a configured expiration interval, and the metadata is signed and persisted
        using the configured key and storage services.

        Bumping 'bin-n' transitively bumps 'snapshot' and 'timestamp' roles.
        """

        # 1. Grab metadata Repository
        metadata_repository = MetadataRepository(
            self._storage_backend, self._key_storage_backend
        )

        # 2. Load Snapshot role.
        snapshot_metadata = metadata_repository.load_role(Role.SNAPSHOT.value)

        # 3. Fore each delegated hashed bin target role, bump and update Snapshot
        hash_bins = self._get_hash_bins()
        for bin_n_name, _ in hash_bins.generate():
            role_metadata = metadata_repository.load_role(bin_n_name)
            metadata_repository.bump_role_version(
                rolename=bin_n_name,
                role_metadata=role_metadata,
                role_expires=self._set_expiration_for_role(Role.BINS.value),
                key_rolename=Role.BIN_N.value,
                store=True,
            )

            snapshot_metadata = metadata_repository.snapshot_update_meta(
                bin_n_name, role_metadata.signed.version, snapshot_metadata
            )

        # 4. Bump Snapshot with updated targets (bin-n) metadata
        self.bump_snapshot(snapshot_metadata)

    def add_hashed_targets(self, targets):
        """
        Update 'bin-n' roles metadata, assigning each passed target to the correct bin.

        Assignment is based on the hash prefix of the target file path. All metadata is
        signed and persisted using the configured key and storage services.

        Updating 'bin-n' transitively bumps 'snapshot' and 'timestamp'.
        """
        hash_bins = self._get_hash_bins()

        targets_payload = dict()
        for target in targets:
            fileinfo = target.get("info")
            filepath = target.get("path")
            delegated_role_bin_name = hash_bins.get_delegate(filepath)
            target_file = TargetFile.from_dict(fileinfo, filepath)
            if targets_payload.get(delegated_role_bin_name) is None:
                targets_payload[delegated_role_bin_name] = list()

            targets_payload[delegated_role_bin_name].append(target_file)

        metadata_repository = MetadataRepository(
            self._storage_backend, self._key_storage_backend
        )

        snapshot_metadata = metadata_repository.add_targets(
            targets_payload,
            Role.BIN_N.value,
        )
        # TODO: Should we renew expiration date of 'timestamp' *and* 'snapshot' here?
        # PEP 458 'Producing Consistent Snapshots' only mentions 'timestamp'.
        # https://www.python.org/dev/peps/pep-0458/#producing-consistent-snapshots
        self.bump_snapshot(snapshot_metadata)
