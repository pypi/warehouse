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


import glob
import os.path
import shutil
import warnings

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from securesystemslib.exceptions import StorageError  # type: ignore
from securesystemslib.interface import (  # type: ignore
    import_ed25519_privatekey_from_file,
)
from securesystemslib.signer import SSlibSigner  # type: ignore
from tuf.api.metadata import (
    SPECIFICATION_VERSION,
    TOP_LEVEL_ROLE_NAMES,
    DelegatedRole,
    Delegations,
    Key,
    Metadata,
    MetaFile,
    Role,
    Root,
    Snapshot,
    SuccinctRoles,
    TargetFile,
    Targets,
    Timestamp,
)
from tuf.api.serialization.json import JSONSerializer
from zope.interface import implementer

from warehouse.config import Environment
from warehouse.tuf.constants import BIN_N_COUNT, Role as RoleType
from warehouse.tuf.interfaces import IKeyService, IRepositoryService, IStorageService

SPEC_VERSION: str = ".".join(SPECIFICATION_VERSION)


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
        Returns a list of ``securesystemslib.signer.Signer`` objects for passed
        TUF role name from configured TUF key path.
        """
        privkey_path = os.path.join(self._key_path, "tufkeys", f"{rolename}*")
        role_keys = glob.glob(privkey_path)
        keys_sslib = [
            SSlibSigner(
                import_ed25519_privatekey_from_file(
                    key, self._request.registry.settings[f"tuf.{rolename}.secret"]
                )
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

        if role == RoleType.TIMESTAMP.value:
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

    def _get_bit_length(self):
        """
        Returns a 'hash bin delegation' management object.
        """
        if self._request.registry.settings["warehouse.env"] == Environment.development:
            bit_length = 8
        else:
            bit_length = BIN_N_COUNT

        return bit_length

    def _is_initialized(self) -> bool:
        """
        Returns True if any top-level role metadata exists, False otherwise.
        """
        try:
            if any(role for role in TOP_LEVEL_ROLE_NAMES if self._load(role)):
                return True
        except StorageError:
            pass

        return False

    def _load(self, role_name: str) -> Metadata:
        """
        Loads latest version of metadata for rolename using configured storage backend.

        NOTE: The storage backend is expected to translate rolenames to filenames and
        figure out the latest version.
        """
        return Metadata.from_file(role_name, None, self._storage_backend)

    def _sign(self, role: Metadata, role_name: str) -> None:
        """
        Re-signs metadata with role-specific key from global key store.

        The metadata role type is used as default key id. This is only allowed for
        top-level roles.
        """
        role.signatures.clear()
        for signer in self._key_storage_backend.get(role_name):
            role.sign(signer, append=True)

    def _persist(self, role: Metadata, role_name: str) -> None:
        """
        Persists metadata using the configured storage backend.

        The metadata role type is used as default role name. This is only allowed for
        top-level roles. All names but 'timestamp' are prefixed with a version number.
        """
        filename = f"{role_name}.json"

        if role_name != RoleType.TIMESTAMP.value:
            filename = f"{role.signed.version}.{filename}"

        role.to_file(filename, JSONSerializer(), self._storage_backend)

    def _bump_expiry(self, role: Metadata, expiry_id: str) -> None:
        """
        Bumps metadata expiration date by role-specific interval.

        The metadata role type is used as default expiry id. This is only allowed for
        top-level roles.
        """
        # FIXME: Review calls to _bump_expiry. Currently, it is called in every
        # update-sign-persist cycle.
        # PEP 458 is unspecific about when to bump expiration, e.g. in the course of a
        # consistent snapshot only 'timestamp' is bumped:
        # https://www.python.org/dev/peps/pep-0458/#producing-consistent-snapshots
        role.signed.expires = datetime.now().replace(microsecond=0) + timedelta(
            seconds=self._request.registry.settings[f"tuf.{expiry_id}.expiry"]
        )

    def _bump_version(self, role: Metadata) -> None:
        """
        Bumps metadata version by 1.
        """
        role.signed.version += 1

    def _update_timestamp(self, snapshot_version: int) -> None:
        """
        Loads 'timestamp', updates meta info about passed 'snapshot' metadata,
        bumps version and expiration, signs and persists.
        """
        timestamp = self._load(Timestamp.type)
        timestamp.signed.snapshot_meta = MetaFile(version=snapshot_version)

        self._bump_version(timestamp)
        self._bump_expiry(timestamp, RoleType.TIMESTAMP.value)
        self._sign(timestamp, RoleType.TIMESTAMP.value)
        self._persist(timestamp, RoleType.TIMESTAMP.value)

    def _update_snapshot(self, targets_meta: List[Tuple[str, int]]) -> int:
        """
        Loads 'snapshot', updates meta info about passed 'targets' metadata, bumps
        version and expiration, signs and persists. Returns new snapshot version, e.g.
        to update 'timestamp'.
        """
        snapshot = self._load(Snapshot.type)

        for name, version in targets_meta:
            snapshot.signed.meta[f"{name}.json"] = MetaFile(version=version)

        self._bump_expiry(snapshot, RoleType.SNAPSHOT.value)
        self._bump_version(snapshot)
        self._sign(snapshot, RoleType.SNAPSHOT.value)
        self._persist(snapshot, RoleType.SNAPSHOT.value)

        return snapshot.signed.version

    def init_dev_repository(self) -> None:
        """
        Creates development TUF top-level role metadata (root, targets, snapshot,
        timestamp).

        FIXME: In production 'root' and 'targets' roles require offline singing keys,
        which may not be available at the time of initializing this metadata.
        """
        # FIXME: Is this a meaningful check? It is rather superficial.
        if self._is_initialized():
            raise FileExistsError("TUF Metadata Repository files already exists.")

        # Bootstrap default top-level metadata to be updated below if necessary
        targets = Targets()
        snapshot = Snapshot()
        timestamp = Timestamp()
        root = Root()

        # Populate public key store, and define trusted signing keys and required
        # signature thresholds for each top-level role in 'root'.
        for role_name in TOP_LEVEL_ROLE_NAMES:
            threshold = self._request.registry.settings[f"tuf.{role_name}.threshold"]
            signers = self._key_storage_backend.get(role_name)

            # FIXME: Is this a meaningful check? Should we check more than just the
            # threshold? And maybe in a different place, e.g. independently of
            # bootstrapping the metadata, because in production we do not have access to
            # all top-level role signing keys at the time of bootstrapping the metadata.
            assert len(signers) >= threshold, (
                f"not enough keys ({len(signers)}) for "
                f"signing threshold '{threshold}'"
            )

            root.roles[role_name] = Role([], threshold)  # type: ignore
            for signer in signers:
                root.add_key(Key.from_securesystemslib_key(signer.key_dict), role_name)

        # Add signature wrapper, bump expiration, and sign and persist
        for role in [targets, snapshot, timestamp, root]:
            metadata = Metadata(role)  # type: ignore
            self._bump_expiry(metadata, role.type)
            self._sign(metadata, role.type)
            self._persist(metadata, role.type)

    def init_targets_delegation(self) -> None:
        """
        Creates TUF metadata for hash bin delegated targets roles (bins, bin-n).

        Metadata is created for one 'bins' role and a configured number of 'bin-n'
        roles. It is populated with configured expiration times, signature thresholds
        and verification keys, and signed and persisted using the configured key and
        storage services.

        FIXME: In production the 'bins' role requires an offline singing key, which may
        not be available at the time of initializing this metadata.

        FIXME: Consider combining 'init_dev_repository' and 'init_targets_delegation'
        to create and persist all initial metadata at once, at version 1.

        """
        # Track names and versions of new and updated targets for 'snapshot' update
        targets_meta = []

        # Update top-level 'targets' role, to delegate trust for all target files to
        # 'bins' role, defining target path patterns, trusted signing keys and required
        # signature thresholds.
        targets = self._load(Targets.type)
        targets.signed.delegations = Delegations(keys={}, roles={})
        targets.signed.delegations.roles[  # type: ignore
            RoleType.BINS.value
        ] = DelegatedRole(
            name=RoleType.BINS.value,
            keyids=[],
            threshold=self._request.registry.settings[
                f"tuf.{RoleType.BINS.value}.threshold"
            ],
            terminating=False,
            paths=["*/*", "*/*/*/*"],
        )

        for signer in self._key_storage_backend.get(RoleType.BINS.value):
            targets.signed.add_key(
                Key.from_securesystemslib_key(signer.key_dict), RoleType.BINS.value
            )

        # Bump version and expiration, and sign and persist updated 'targets'.
        self._bump_version(targets)
        self._bump_expiry(targets, RoleType.TARGETS.value)
        self._sign(targets, RoleType.TARGETS.value)
        self._persist(targets, RoleType.TARGETS.value)

        targets_meta.append((RoleType.TARGETS.value, targets.signed.version))

        succinct_roles = SuccinctRoles(
            [], 1, self._get_bit_length(), RoleType.BIN_N.value
        )
        # Create new 'bins' role and delegate trust from 'bins' for all target files to
        # 'bin-n' roles based on file path hash prefixes, a.k.a hash bin delegation.
        bins = Metadata(Targets())
        bins.signed.delegations = Delegations(keys={}, succinct_roles=succinct_roles)
        for delegated_name in succinct_roles.get_roles():
            for signer in self._key_storage_backend.get(RoleType.BIN_N.value):
                bins.signed.add_key(
                    Key.from_securesystemslib_key(signer.key_dict), delegated_name
                )
            bin_n = Metadata(Targets())
            self._bump_expiry(bin_n, RoleType.BIN_N.value)
            self._sign(bin_n, RoleType.BIN_N.value)
            self._persist(bin_n, delegated_name)

        # Bump expiration, and sign and persist new 'bins' role.
        self._bump_expiry(bins, RoleType.BINS.value)
        self._sign(bins, RoleType.BINS.value)
        self._persist(bins, RoleType.BINS.value)

        targets_meta.append((RoleType.BINS.value, bins.signed.version))

        self._update_timestamp(self._update_snapshot(targets_meta))

    def add_hashed_targets(self, targets: List[TargetFile]) -> None:
        """
        Updates 'bin-n' roles metadata, assigning each passed target to the correct bin.

        Assignment is based on the hash prefix of the target file path. All metadata is
        signed and persisted using the configured key and storage services.

        Updating 'bin-n' also updates 'snapshot' and 'timestamp'.
        """
        # Group target files by responsible 'bin-n' roles
        bin_n = self._load(RoleType.BINS.value)
        bin_n_succinct_roles = bin_n.signed.delegations.succinct_roles
        bin_n_target_groups: Dict[str, List[TargetFile]] = {}

        for target in targets:
            bin_n_name = bin_n_succinct_roles.get_role_for_target(target.path)

            if bin_n_name not in bin_n_target_groups:
                bin_n_target_groups[bin_n_name] = []

            bin_n_target_groups[bin_n_name].append(target)

        # Update target file info in responsible 'bin-n' roles, bump version and expiry
        # and sign and persist
        targets_meta = []
        for bin_n_name, target_files in bin_n_target_groups.items():
            bin_n = self._load(bin_n_name)

            for target_file in target_files:
                bin_n.signed.targets[target_file.path] = target_file

            self._bump_expiry(bin_n, RoleType.BIN_N.value)
            self._bump_version(bin_n)
            self._sign(bin_n, RoleType.BIN_N.value)
            self._persist(bin_n, bin_n_name)

            targets_meta.append((bin_n_name, bin_n.signed.version))

        self._update_timestamp(self._update_snapshot(targets_meta))

    def bump_bin_n_roles(self) -> None:
        """
        Bumps version and expiration date of 'bin-n' role metadata (multiple).

        The version numbers are incremented by one, the expiration dates are renewed
        using a configured expiration interval, and the metadata is signed and persisted
        using the configured key and storage services.

        Updating 'bin-n' also updates 'snapshot' and 'timestamp'.
        """
        bin_n = self._load(RoleType.BINS.value)
        bin_n_succinct_roles = bin_n.signed.delegations.succinct_roles
        targets_meta = []
        for bin_n_name in bin_n_succinct_roles.get_roles():
            bin_n = self._load(bin_n_name)

            self._bump_expiry(bin_n, RoleType.BIN_N.value)
            self._bump_version(bin_n)
            self._sign(bin_n, RoleType.BIN_N.value)
            self._persist(bin_n, bin_n_name)

            targets_meta.append((bin_n_name, bin_n.signed.version))

        self._update_timestamp(self._update_snapshot(targets_meta))

    def bump_snapshot(self) -> None:
        """
        Bumps version and expiration date of TUF 'snapshot' role metadata.

        The version number is incremented by one, the expiration date renewed using a
        configured expiration interval, and the metadata is signed and persisted using
        the configured key and storage services.

        Updating 'snapshot' also updates 'timestamp'.
        """
        self._update_timestamp(self._update_snapshot([]))
