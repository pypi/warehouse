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

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from securesystemslib.exceptions import StorageError
from securesystemslib.signer import SSlibSigner
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
    StorageBackendInterface,
    TargetFile,
    Targets,
    Timestamp,
)
from tuf.api.serialization.json import JSONSerializer

from warehouse.tuf.interfaces import IKeyService

SPEC_VERSION = ".".join(SPECIFICATION_VERSION)


@dataclass
class RolesPayload:
    """
    Container for various role data.

    This includes data that can be assigned to any role (``expiration`` and
    ``threshold``), data that can only be assigned to delegating roles
    (``delegation_role``, ``paths``, ``path_hash_prefixes`` and the keyids or public
    portions of ``keys``), and data that is used to sign any roles (private portion of
    ``keys``).

    """

    expiration: datetime
    threshold: int
    keys: List[Dict[str, Any]]
    delegation_role: str = None
    paths: List[str] = None
    path_hash_prefixes: List[str] = None


@dataclass
class TargetsPayload:
    """
    Container for target files info, suitable for targets metadata.
    """

    fileinfo: str
    path: str


class MetadataRepository:
    """
    TUF metadata repository abstraction to create and maintain role metadata.
    """

    def __init__(
        self,
        storage_backend: StorageBackendInterface,
        key_backend: IKeyService,
    ):
        self.storage_backend: StorageBackendInterface = storage_backend
        self.key_backend: IKeyService = key_backend

    @property
    def is_initialized(self) -> bool:
        """
        Repository state based on metadata availability in storage.
        """
        try:
            if any(role for role in TOP_LEVEL_ROLE_NAMES if self.load_role(role)):
                return True
        except StorageError:
            pass

        return False

    def _create_delegated_targets_roles(
        self,
        delegator_metadata: Metadata,
        delegate_role_parameters: List[RolesPayload],
        snapshot_metadata: Optional[Metadata[Snapshot]] = None,
    ) -> Metadata[Snapshot]:
        """
        Creates delegated targets roles metadata and updates delegator and snapshot.
        """
        if snapshot_metadata is None:
            snapshot_metadata = self.load_role(Snapshot.type)

        for role_parameter in delegate_role_parameters:
            rolename = role_parameter.delegation_role
            try:
                if self.load_role(rolename):
                    raise FileExistsError(f"Role {rolename} already exists.")
            except StorageError:
                pass

            delegated_role = DelegatedRole(
                name=rolename,
                keyids=[key["keyid"] for key in role_parameter.keys],
                threshold=role_parameter.threshold,
                terminating=None,
                paths=role_parameter.paths,
                path_hash_prefixes=role_parameter.path_hash_prefixes,
            )

            if delegator_metadata.signed.delegations is None:
                delegation = self._build_delegations(
                    rolename, delegated_role, role_parameter.keys
                )
                delegator_metadata.signed.delegations = delegation
            else:
                delegator_metadata.signed.delegations.roles[rolename] = delegated_role

            targets = Targets(1, SPEC_VERSION, role_parameter.expiration, {}, None)
            role_metadata = Metadata(targets, {})

            for key in role_parameter.keys:
                delegator_metadata.signed.add_key(
                    rolename, Key.from_securesystemslib_key(key)
                )
                role_metadata.sign(SSlibSigner(key), append=True)

            self._store(rolename, role_metadata)
            snapshot_metadata = self.snapshot_update_meta(
                rolename, role_metadata.signed.version, snapshot_metadata
            )

        return snapshot_metadata

    def _filename(self, rolename: str, version: int) -> str:
        """
        Builds metadata filename with passed role name and metadata version.
        """
        if rolename == Timestamp.type:
            filename = f"{rolename}.json"
        else:
            filename = f"{version}.{rolename}.json"

        return filename

    def _store(self, rolename: str, metadata: Metadata) -> None:
        """
        Writes role metadata to storage using the configured backend.
        """
        filename = self._filename(rolename, metadata.signed.version)
        metadata.to_file(filename, JSONSerializer(), self.storage_backend)

    def _build_delegations(
        self, rolename: str, delegated_role: DelegatedRole, keys: List[Dict[str, Any]]
    ) -> Delegations:
        """
        Returns ``Delegations`` object assigning passed keys and roles information.
        """
        return Delegations(
            keys={key["keyid"]: Key.from_securesystemslib_key(key) for key in keys},
            roles={rolename: delegated_role},
        )

    def initialize(
        self, payload: Dict[str, RolesPayload], store: Optional[bool]
    ) -> Dict[str, Metadata]:
        """
        Initializes metadata repository with basic top-level role metadata.

        Args:
            payload: Initial per-role infos to populate metadata.
            store: Indicates whether metadata should be written to storage.

        Raises:
            FileExistsError: Repository is already initialized.
            ValueError: Not enough signing keys for the signature threshold of a role.

        Returns:
            Dictionary of role names as keys and metadata objects as values.
            ``Dict[str, Metadata]``
        """
        top_level_roles_metadata = dict()
        if self.is_initialized:
            raise FileExistsError("Metadata already exists in the Storage Service")

        targets = Targets(1, SPEC_VERSION, payload[Targets.type].expiration, {}, None)
        targets_metadata = Metadata(targets, {})
        top_level_roles_metadata[Targets.type] = targets_metadata

        meta = {"targets.json": MetaFile(targets.version)}
        snapshot = Snapshot(1, SPEC_VERSION, payload[Snapshot.type].expiration, meta)
        snapshot_metadata = Metadata(snapshot, {})
        top_level_roles_metadata[Snapshot.type] = snapshot_metadata

        snapshot_meta = MetaFile(snapshot.version)
        timestamp = Timestamp(
            1, SPEC_VERSION, payload[Timestamp.type].expiration, snapshot_meta
        )
        timestamp_metadata = Metadata(timestamp, {})
        top_level_roles_metadata[Timestamp.type] = timestamp_metadata

        roles = {
            role_name: Role([], payload[role_name].threshold)
            for role_name in TOP_LEVEL_ROLE_NAMES
        }
        root = Root(1, SPEC_VERSION, payload[Root.type].expiration, {}, roles, True)

        # Sign all top level roles metadata
        signers = dict()
        for role in TOP_LEVEL_ROLE_NAMES:
            if payload[role].threshold > len(payload[role].keys):
                raise ValueError(
                    f"Role {role} has missing Key(s) "
                    f"to match to defined threshold {payload[role].threshold}."
                )

            for key in payload[role].keys:
                root.add_key(role, Key.from_securesystemslib_key(key))

            signers[role] = {
                key["keyid"]: SSlibSigner(key) for key in payload[role].keys
            }

        root_metadata = Metadata(root, {})
        top_level_roles_metadata[Root.type] = root_metadata
        for role in signers:
            for signer in signers[role].values():
                top_level_roles_metadata[role].sign(signer, append=True)

            if store:
                self._store(role, top_level_roles_metadata[role])

        return top_level_roles_metadata

    def load_role(self, rolename: str) -> Metadata:
        """
        Loads latest version of metadata for rolename using configured storage backend.

        NOTE: The storage backend is expected to translate rolenames to filenames.

        Returns:
            Role metadata
            ``tuf.api.metadata.Metadata``
        """
        return Metadata.from_file(rolename, None, self.storage_backend)

    def delegate_targets_roles(
        self,
        payload: Dict[str, List[RolesPayload]],
    ) -> Metadata[Snapshot]:
        """
        Performs targets delegation for delegator-to-delegates items in passed payload.

        Creates new basic delegate metadata, configures delegation in delegator metadata
        and bumps its version, and updates snapshot metadata accordingly.

        Args:
            payload: Dictionary of delegator role names as keys and lists of
                    per-delegate info to populate the delegate metadata.

        Raises:
            FileExistsError: Delegate metadata already exists.

        Returns:
            Updated snapshot metadata
            ``tuf.api.metadata.Metadata[Snapshot]``
        """

        snapshot_metadata = self.load_role(Snapshot.type)
        for delegator, delegate_role_parameters in payload.items():
            delegator_metadata = self.load_role(delegator)
            snapshot_metadata = self._create_delegated_targets_roles(
                delegator_metadata,
                delegate_role_parameters,
                snapshot_metadata,
            )
            delegator_metadata = self.bump_role_version(
                rolename=delegator,
                role_metadata=delegator_metadata,
                role_expires=delegator_metadata.signed.expires,
                key_rolename=None,
                store=True,
            )
            snapshot_metadata = self.snapshot_update_meta(
                delegator, delegator_metadata.signed.version, snapshot_metadata
            )

        return snapshot_metadata

    def bump_role_version(
        self,
        rolename: str,
        role_metadata: Metadata,
        role_expires: datetime,
        key_rolename: Optional[str] = None,
        store: Optional[bool] = False,
    ) -> Metadata:
        """
        Bumps metadata version by one and assigns new expiration date for passed role.

        Args:
            rolename: Used to associate signing key and (optionally) store metadata.
            role_metadata: Role metadata to be bumped.
            role_expires: New role expiration date.
            key_rolename: Used to associate a signing key by a name other than rolename.
            store: Indicates whether metadata should be written to storage.

        Returns:
            Updated metadata
            ``tuf.api.metadata.Metadata``
        """
        if key_rolename:
            key_rolename = key_rolename
        else:
            key_rolename = rolename
        role_metadata.signed.expires = role_expires
        role_metadata.signed.version += 1
        key_rolename_keys = self.key_backend.get(key_rolename)
        for key in key_rolename_keys:
            role_metadata.sign(SSlibSigner(key), append=True)

        if store:
            self._store(rolename, role_metadata)

        return role_metadata

    def timestamp_bump_version(
        self,
        snapshot_version: int,
        timestamp_expires: datetime,
        store: bool = False,
    ) -> Metadata[Timestamp]:
        """
        Bumps timestamp metadata version by one and assigns new expiration date.

        Args:
            snapshot_version: New snapshot version for timestamp meta field.
            timestamp_expires: New timestamp expiration date.
            store: Indicates whether metadata should be written to storage.

        Returns:
            Updated timestamp metadata
            ``tuf.api.metadata.Metadata[Timestamp]``
        """
        timestamp_metadata = self.load_role(Timestamp.type)
        timestamp_metadata.signed.version += 1
        timestamp_metadata.signed.expires = timestamp_expires
        timestamp_metadata.signed.snapshot_meta = MetaFile(version=snapshot_version)
        timestamp_keys = self.key_backend.get(Timestamp.type)
        for key in timestamp_keys:
            timestamp_metadata.sign(SSlibSigner(key), append=True)

        if store:
            self._store(Timestamp.type, timestamp_metadata)

        return timestamp_metadata

    def snapshot_bump_version(
        self,
        snapshot_expires: datetime,
        snapshot_metadata: Optional[Metadata[Snapshot]] = None,
        store: Optional[bool] = False,
    ) -> Metadata[Snapshot]:
        """
        Bumps snapshot metadata version by one and assigns new expiration date.

        Args:
            snapshot_expires: New snapshot expiration date.
            snapshot_metadata: Snapshot metadata to be bumped. If not passed, snapshot
                    metadata is loaded from storage.
            store: Indicates whether updated snapshot metadata should be written to
                    storage.

        Returns:
            Updated snapshot metadata
            ``tuf.api.metadata.Metadata[Snapshot]``
        """
        if snapshot_metadata is None:
            snapshot_metadata = self.load_role(Snapshot.type)

        snapshot_metadata.signed.version += 1
        snapshot_metadata.signed.expires = snapshot_expires
        snapshot_keys = self.key_backend.get(Snapshot.type)
        for key in snapshot_keys:
            snapshot_metadata.sign(SSlibSigner(key), append=True)

        if store is True:
            self._store(Snapshot.type, snapshot_metadata)

        return snapshot_metadata

    def snapshot_update_meta(
        self,
        meta_role_name: str,
        meta_role_version: int,
        snapshot_metadata: Optional[Metadata[Snapshot]] = None,
    ) -> Metadata[Snapshot]:
        """
        Adds targets metadata information to snapshot metadata.

        Args:
            meta_role_name: Targets metadata name to be added to snapshot.
            meta_role_version: Targets metadata version to be added to snapshot.
            snapshot_metadata: Snapshot metadata to be updated. If not passed, snapshot
                    metadata is loaded from storage.

        Return:
            Updated snapshot metadata
            ``tuf.api.metadata.Metadata[Snapshot]``
        """
        if snapshot_metadata is None:
            snapshot_metadata = self.load_role(Snapshot.type)

        snapshot_metadata.signed.meta[f"{meta_role_name}.json"] = MetaFile(
            version=meta_role_version
        )

        return snapshot_metadata

    def add_targets(
        self,
        payload: Dict[str, List[TargetsPayload]],
        key_rolename: str,
    ) -> Metadata[Snapshot]:
        """
        Adds target files info to targets metadata and updates snapshot.

        The targets metadata is loaded from storage, assigned the passed target files
        info, has its version incremented by one, and is signed and written back
        to storage. Snapshot, also loaded from storage, is updated with the new targets
        metadata versions.

        NOTE: Snapshot metadata version is not updated.

        Args:
            payload: Dictionary of targets role names as keys and lists of target file
                    info objects.
            key_rolename: Targets metadata signing key in key storage.

        Returns:
            Updated snapshot metadata
            ``tuf.api.metadata.Metadata[Snapshot]``
        """
        snapshot_metadata = self.load_role(Snapshot.type)

        for rolename, targets in payload.items():
            role_metadata = self.load_role(rolename)
            for target in targets:
                target_file = TargetFile.from_dict(target.fileinfo, target.path)
                role_metadata.signed.targets[target.path] = target_file

            role_metadata.signed.version += 1
            role_keys = self.key_backend.get(key_rolename)
            for key in role_keys:
                role_metadata.sign(SSlibSigner(key), append=True)

            self._store(rolename, role_metadata)
            role_metadata = self.bump_role_version(
                rolename=rolename,
                role_metadata=role_metadata,
                role_expires=role_metadata.signed.expires,
                key_rolename=key_rolename,
                store=True,
            )
            snapshot_metadata = self.snapshot_update_meta(
                rolename, role_metadata.signed.version, snapshot_metadata
            )

        return snapshot_metadata
