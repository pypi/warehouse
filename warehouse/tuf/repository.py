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

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from securesystemslib.exceptions import StorageError  # type: ignore
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
    StorageBackendInterface,
    TargetFile,
    Targets,
    Timestamp,
)
from tuf.api.serialization.json import JSONSerializer

from warehouse.tuf.interfaces import IKeyService

SPEC_VERSION = ".".join(SPECIFICATION_VERSION)


class MetadataRepository:
    """
    TUF metadata repository abstraction to create and maintain role metadata.
    """

    def __init__(
        self,
        storage_backend: StorageBackendInterface,
        key_backend: IKeyService,
        settings: Dict,
    ):
        self.storage_backend: StorageBackendInterface = storage_backend
        self.key_backend: IKeyService = key_backend
        self.settings: Dict = settings

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

    def _set_expiration_for_role(self, role_name):
        """
        Returns a metadata expiration date (now + role-specific interval).
        """
        return datetime.now().replace(microsecond=0) + timedelta(
            seconds=self.settings[f"tuf.{role_name}.expiry"]
        )

    def _create_delegated_targets_roles(
        self,
        delegator_metadata: Metadata,
        delegatees: List[Tuple[DelegatedRole, List[Dict[str, Any]], datetime]],
        snapshot_metadata: Optional[Metadata[Snapshot]] = None,
    ) -> Metadata[Snapshot]:
        """
        Creates delegated targets roles metadata and updates delegator and snapshot.
        """
        if snapshot_metadata is None:
            snapshot_metadata = self.load_role(Snapshot.type)

        for delegatee, keys, expiration in delegatees:

            if delegator_metadata.signed.delegations is None:
                delegator_metadata.signed.delegations = Delegations(
                    {key["keyid"]: Key.from_securesystemslib_key(key) for key in keys},
                    {delegatee.name: delegatee},
                )
            else:
                delegator_metadata.signed.delegations.roles[delegatee.name] = delegatee

            targets = Targets(1, SPEC_VERSION, expiration, {}, None)
            role_metadata = Metadata(targets, {})

            for key in keys:
                delegator_metadata.signed.add_key(
                    delegatee.name, Key.from_securesystemslib_key(key)
                )
                role_metadata.sign(SSlibSigner(key), append=True)

            self._store(delegatee.name, role_metadata)

            snapshot_metadata = self.snapshot_update_meta(
                delegatee.name, role_metadata.signed.version, snapshot_metadata
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

    def initialize(
        self, keys: Dict[str, List[Dict[str, Any]]], store: Optional[bool]
    ) -> Dict[str, Metadata]:
        """
        Initializes metadata repository with basic top-level role metadata.

        Args:
            keys: per-role keys for signing.
            store: Indicates whether metadata should be written to storage.

        Raises:
            FileExistsError: Repository is already initialized.
            ValueError: Not enough signing keys for the signature threshold of a role.

        Returns:
            Dictionary of role names as keys and metadata objects as values.
            ``Dict[str, Metadata]``
        """
        top_level_roles_metadata: Dict[str, Any] = dict()
        if self.is_initialized:
            raise FileExistsError("Metadata already exists in the Storage Service")

        targets = Targets(
            1, SPEC_VERSION, self._set_expiration_for_role(Targets.type), {}, None
        )
        targets_metadata = Metadata(targets, {})
        top_level_roles_metadata[Targets.type] = targets_metadata

        meta = {"targets.json": MetaFile(targets.version)}
        snapshot = Snapshot(
            1, SPEC_VERSION, self._set_expiration_for_role(Snapshot.type), meta
        )
        snapshot_metadata = Metadata(snapshot, {})
        top_level_roles_metadata[Snapshot.type] = snapshot_metadata

        snapshot_meta = MetaFile(snapshot.version)
        timestamp = Timestamp(
            1,
            SPEC_VERSION,
            self._set_expiration_for_role(Timestamp.type),
            snapshot_meta,
        )
        timestamp_metadata = Metadata(timestamp, {})
        top_level_roles_metadata[Timestamp.type] = timestamp_metadata

        roles = {
            role_name: Role([], self.settings[f"tuf.{role_name}.threshold"])
            for role_name in TOP_LEVEL_ROLE_NAMES
        }
        root = Root(
            1, SPEC_VERSION, self._set_expiration_for_role(Root.type), {}, roles, True
        )

        # Sign all top level roles metadata
        signers = dict()
        for role in TOP_LEVEL_ROLE_NAMES:
            role_keys = keys[role]
            if self.settings[f"tuf.{role}.threshold"] > len(role_keys):
                raise ValueError(
                    f"Role {role} has missing Key(s) "
                    f"to match to defined threshold "
                    f"{self.settings[f'tuf.{role}.threshold']}."
                )

            for key in role_keys:
                root.add_key(role, Key.from_securesystemslib_key(key))

            signers[role] = {key["keyid"]: SSlibSigner(key) for key in role_keys}

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
        payload: Dict[str, List[Tuple[DelegatedRole, List[Dict[str, Any]], datetime]]],
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
        for delegator, delegatee in payload.items():
            delegator_metadata = self.load_role(delegator)
            snapshot_metadata = self._create_delegated_targets_roles(
                delegator_metadata,
                delegatee,
                snapshot_metadata,
            )
            delegator_metadata = self.bump_role_version(
                rolename=delegator,
                role_metadata=delegator_metadata,
                role_expires=self._set_expiration_for_role(delegator),
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
        timestamp_metadata.signed.expires = self._set_expiration_for_role(
            Timestamp.type
        )
        timestamp_metadata.signed.snapshot_meta = MetaFile(version=snapshot_version)
        timestamp_keys = self.key_backend.get(Timestamp.type)
        for key in timestamp_keys:
            timestamp_metadata.sign(SSlibSigner(key), append=True)

        if store:
            self._store(Timestamp.type, timestamp_metadata)

        return timestamp_metadata

    def snapshot_bump_version(
        self,
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
        snapshot_metadata.signed.expires = self._set_expiration_for_role(Snapshot.type)
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
        payload: Dict[str, List[TargetFile]],
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
                role_metadata.signed.targets[target.path] = target

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
