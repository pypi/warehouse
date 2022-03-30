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

import pretend
import pytest

from securesystemslib.exceptions import StorageError
from tuf.api.metadata import (
    TOP_LEVEL_ROLE_NAMES,
    DelegatedRole,
    Delegations,
    MetaFile,
    Snapshot,
    StorageBackendInterface,
)

from warehouse.tuf import repository
from warehouse.tuf.interfaces import IKeyService


class TestMetadataRepository:
    def test_basic_init(self, tuf_repository):
        class FakeStorageBackend(StorageBackendInterface):
            pass

        class FakeKeyBackend(IKeyService):
            pass

        tuf_repository = repository.MetadataRepository(
            FakeStorageBackend, FakeKeyBackend
        )
        assert tuf_repository.storage_backend == FakeStorageBackend
        assert tuf_repository.key_backend == FakeKeyBackend

    def test_is_initialized(self, tuf_repository):

        tuf_repository.load_role = pretend.call_recorder(lambda role: None)

        assert tuf_repository.is_initialized is False

        for role in TOP_LEVEL_ROLE_NAMES:
            assert pretend.call(role) in tuf_repository.load_role.calls

    def test_is_initialized_load_metadata(self, tuf_repository):
        tuf_repository.load_role = pretend.call_recorder(lambda role: True)
        assert tuf_repository.is_initialized is True
        assert tuf_repository.load_role.calls[0] in [
            pretend.call("targets"),
            pretend.call("root"),
            pretend.call("snapshot"),
            pretend.call("timestamp"),
        ]

    def test_is_initialized_cannot_load_metadata(self, tuf_repository):
        tuf_repository.load_role = pretend.call_recorder(lambda role: None)
        assert tuf_repository.is_initialized is False
        assert tuf_repository.load_role.calls[0] in [
            pretend.call("targets"),
            pretend.call("root"),
            pretend.call("snapshot"),
            pretend.call("timestamp"),
        ]

    def test_is_initialized_raise_storageerror(self, tuf_repository):
        tuf_repository.load_role = pretend.call_recorder(pretend.raiser(StorageError))
        assert tuf_repository.is_initialized is False
        assert tuf_repository.load_role.calls[0] in [
            pretend.call("targets"),
            pretend.call("root"),
            pretend.call("snapshot"),
            pretend.call("timestamp"),
        ]

    def test__create_delegated_targets_roles(self, tuf_repository, monkeypatch):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_targets_md = pretend.stub(
            signed=pretend.stub(
                delegations=None, add_key=pretend.call_recorder(lambda *a, **kw: None)
            )
        )
        fake_snapshot_md = pretend.stub(signed=pretend.stub(meta={}))

        tuf_repository.load_role = pretend.call_recorder(
            lambda role: fake_snapshot_md if role == Snapshot.type else None
        )
        tuf_repository._build_delegations = pretend.call_recorder(
            lambda *a, **kw: "delegation"
        )
        tuf_repository._store = pretend.call_recorder(lambda *a, **kw: None)

        test_delegate_roles_parameters = [
            repository.RolesPayload(
                fake_time,
                1,
                [{"keyid": "key1"}, {"keyid": "key2"}],
                "test_bin",
                paths=["*/*"],
            )
        ]

        fake_metadata = pretend.stub(
            sign=pretend.call_recorder(lambda *a, **kw: None),
            signed=pretend.stub(version=3),
        )
        monkeypatch.setattr(
            "warehouse.tuf.repository.Metadata", lambda *a, **kw: fake_metadata
        )
        monkeypatch.setattr(
            "warehouse.tuf.repository.Key.from_securesystemslib_key",
            lambda *a, **kw: None,
        )
        result = tuf_repository._create_delegated_targets_roles(
            delegator_metadata=fake_targets_md,
            delegate_role_parameters=test_delegate_roles_parameters,
        )

        assert "test_bin.json" in result.signed.meta
        assert tuf_repository.load_role.calls == [
            pretend.call(Snapshot.type),
            pretend.call("test_bin"),
        ]
        assert tuf_repository._build_delegations.calls[0].args[0] == "test_bin"
        assert type(tuf_repository._build_delegations.calls[0].args[1]) == DelegatedRole
        assert tuf_repository._build_delegations.calls[0].args[2] == [
            {"keyid": "key1"},
            {"keyid": "key2"},
        ]
        assert tuf_repository._store.calls[0].args[0] == "test_bin"

    def test__create_delegated_targets_roles_with_snapshot_md(
        self, tuf_repository, monkeypatch
    ):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_targets_md = pretend.stub(
            signed=pretend.stub(
                delegations=None, add_key=pretend.call_recorder(lambda *a, **kw: None)
            )
        )
        fake_snapshot_md = pretend.stub(signed=pretend.stub(meta={}))

        tuf_repository.load_role = pretend.call_recorder(
            lambda role: fake_snapshot_md if role == Snapshot.type else None
        )
        tuf_repository._build_delegations = pretend.call_recorder(
            lambda *a, **kw: "delegation"
        )
        tuf_repository._store = pretend.call_recorder(lambda *a, **kw: None)

        test_delegate_roles_parameters = [
            repository.RolesPayload(
                fake_time,
                1,
                [{"keyid": "key1"}, {"keyid": "key2"}],
                "test_bin",
                paths=["*/*"],
            )
        ]

        fake_metadata = pretend.stub(
            sign=pretend.call_recorder(lambda *a, **kw: None),
            signed=pretend.stub(version=3),
        )
        monkeypatch.setattr(
            "warehouse.tuf.repository.Metadata", lambda *a, **kw: fake_metadata
        )
        monkeypatch.setattr(
            "warehouse.tuf.repository.Key.from_securesystemslib_key",
            lambda *a, **kw: None,
        )
        result = tuf_repository._create_delegated_targets_roles(
            delegator_metadata=fake_targets_md,
            delegate_role_parameters=test_delegate_roles_parameters,
            snapshot_metadata=fake_snapshot_md,
        )

        assert "test_bin.json" in result.signed.meta
        assert tuf_repository.load_role.calls == [
            pretend.call("test_bin"),
        ]
        assert tuf_repository._build_delegations.calls[0].args[0] == "test_bin"
        assert type(tuf_repository._build_delegations.calls[0].args[1]) == DelegatedRole
        assert tuf_repository._build_delegations.calls[0].args[2] == [
            {"keyid": "key1"},
            {"keyid": "key2"},
        ]
        assert tuf_repository._store.calls[0].args[0] == "test_bin"

    def test__create_delegated_targets_roles_raises_storageerror(
        self, tuf_repository, monkeypatch
    ):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_targets_md = pretend.stub(
            signed=pretend.stub(
                delegations=None, add_key=pretend.call_recorder(lambda *a, **kw: None)
            )
        )
        fake_snapshot_md = pretend.stub(signed=pretend.stub(meta={}))

        tuf_repository.load_role = pretend.raiser(StorageError())
        tuf_repository._build_delegations = pretend.call_recorder(
            lambda *a, **kw: "delegation"
        )
        tuf_repository._store = pretend.call_recorder(lambda *a, **kw: None)

        test_delegate_roles_parameters = [
            repository.RolesPayload(
                fake_time,
                1,
                [{"keyid": "key1"}, {"keyid": "key2"}],
                "test_bin",
                paths=["*/*"],
            )
        ]

        fake_metadata = pretend.stub(
            sign=pretend.call_recorder(lambda *a, **kw: None),
            signed=pretend.stub(version=3),
        )
        monkeypatch.setattr(
            "warehouse.tuf.repository.Metadata", lambda *a, **kw: fake_metadata
        )
        monkeypatch.setattr(
            "warehouse.tuf.repository.Key.from_securesystemslib_key",
            lambda *a, **kw: None,
        )
        result = tuf_repository._create_delegated_targets_roles(
            delegator_metadata=fake_targets_md,
            delegate_role_parameters=test_delegate_roles_parameters,
            snapshot_metadata=fake_snapshot_md,
        )

        assert "test_bin.json" in result.signed.meta
        assert tuf_repository._build_delegations.calls[0].args[0] == "test_bin"
        assert type(tuf_repository._build_delegations.calls[0].args[1]) == DelegatedRole
        assert tuf_repository._build_delegations.calls[0].args[2] == [
            {"keyid": "key1"},
            {"keyid": "key2"},
        ]
        assert tuf_repository._store.calls[0].args[0] == "test_bin"

    def test__create_delegated_targets_roles_raise_fileexists(
        self, tuf_repository, monkeypatch
    ):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_targets_md = pretend.stub(
            signed=pretend.stub(
                delegations=None, add_key=pretend.call_recorder(lambda *a, **kw: None)
            )
        )
        fake_snapshot_md = pretend.stub(signed=pretend.stub(meta={}))

        tuf_repository.load_role = pretend.call_recorder(
            lambda role: fake_snapshot_md if role == Snapshot.type else True
        )
        test_delegate_roles_parameters = [
            repository.RolesPayload(
                fake_time,
                1,
                [{"keyid": "key1"}, {"keyid": "key2"}],
                "test_bin",
                paths=["*/*"],
            )
        ]

        with pytest.raises(FileExistsError) as err:
            tuf_repository._create_delegated_targets_roles(
                delegator_metadata=fake_targets_md,
                delegate_role_parameters=test_delegate_roles_parameters,
                snapshot_metadata=fake_snapshot_md,
            )

        assert "Role test_bin already exists." in str(err.value)
        assert tuf_repository.load_role.calls == [pretend.call("test_bin")]

    def test__create_delegated_targets_roles_has_delegations(
        self, tuf_repository, monkeypatch
    ):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_targets_md = pretend.stub(
            signed=pretend.stub(
                delegations=pretend.stub(roles={"role1": "delegated_stuff"}),
                add_key=pretend.call_recorder(lambda *a, **kw: None),
            )
        )
        fake_snapshot_md = pretend.stub(signed=pretend.stub(meta={}))

        tuf_repository.load_role = pretend.call_recorder(
            lambda role: fake_snapshot_md if role == Snapshot.type else None
        )
        tuf_repository._store = pretend.call_recorder(lambda *a, **kw: None)

        test_delegate_roles_parameters = [
            repository.RolesPayload(
                fake_time,
                1,
                [{"keyid": "key1"}, {"keyid": "key2"}],
                "test_bin",
                paths=["*/*"],
            )
        ]

        fake_metadata = pretend.stub(
            sign=pretend.call_recorder(lambda *a, **kw: None),
            signed=pretend.stub(version=3),
        )
        monkeypatch.setattr(
            "warehouse.tuf.repository.Metadata", lambda *a, **kw: fake_metadata
        )
        monkeypatch.setattr(
            "warehouse.tuf.repository.Key.from_securesystemslib_key",
            lambda *a, **kw: None,
        )
        result = tuf_repository._create_delegated_targets_roles(
            delegator_metadata=fake_targets_md,
            delegate_role_parameters=test_delegate_roles_parameters,
        )

        assert "test_bin.json" in result.signed.meta
        assert tuf_repository.load_role.calls == [
            pretend.call(Snapshot.type),
            pretend.call("test_bin"),
        ]
        assert "role1" in fake_targets_md.signed.delegations.roles.keys()
        assert "test_bin" in fake_targets_md.signed.delegations.roles.keys()
        assert tuf_repository._store.calls[0].args[0] == "test_bin"

    def test__filename(self, tuf_repository):

        assert tuf_repository._filename("root", 1) == "1.root.json"
        assert tuf_repository._filename("root", 2) == "2.root.json"
        assert tuf_repository._filename("snapshot", 2) == "2.snapshot.json"
        assert tuf_repository._filename("timestamp", 2) == "timestamp.json"
        assert tuf_repository._filename("timestamp", 3) == "timestamp.json"

    def test__store(self, tuf_repository):
        fake_metadata = pretend.stub(
            to_file=pretend.call_recorder(lambda *a, **kw: None),
            signed=pretend.stub(version=1),
        )

        result = tuf_repository._store("root", fake_metadata)

        assert result is None
        assert fake_metadata.to_file.calls[0].args[0] == "1.root.json"

    def test__build_delegations(self, tuf_repository, monkeypatch):

        fake_delegated_role = DelegatedRole(
            name="xxxx-yyyy",
            keyids=["fake_key1", "fake_key2"],
            threshold=1,
            terminating=None,
            paths=None,
            path_hash_prefixes=["00-07"],
        )

        monkeypatch.setattr(
            "warehouse.tuf.repository.Key.from_securesystemslib_key",
            lambda *a, **kw: {"key": "data"},
        )
        result = tuf_repository._build_delegations(
            "00-07", fake_delegated_role, [{"keyid": "key1"}, {"keyid": "key2"}]
        )

        assert type(result) == Delegations
        assert "00-07" in result.roles.keys()
        assert result.keys == {"key1": {"key": "data"}, "key2": {"key": "data"}}

    def test_initialization(self, tuf_repository):
        fake_key = {
            "keytype": "ed25519",
            "scheme": "ed25519",
            "keyid": (
                "6dcd53f0a90fca17700f819e939a74b133aa5cd8619f3dc03228c0c68dcc2abb"
            ),
            "keyid_hash_algorithms": ["sha256", "sha512"],
            "keyval": {
                "public": (
                    "c864d93b521d5851275a7b7c79fb0ac76311c206262eabd67319eba6665b1417"
                ),
                "private": (
                    "bbe40143bfe1a3b6a41647f590e398fb8dd38fddf6b279edefdc022cdb649cdc"
                ),
            },
        }
        top_roles_payload = dict()
        for role in TOP_LEVEL_ROLE_NAMES:
            top_roles_payload[role] = repository.RolesPayload(
                expiration=datetime.datetime(2019, 6, 16, 9, 5, 1),
                threshold=1,
                keys=[fake_key],
            )

        tuf_repository.load_role = pretend.call_recorder(lambda *a, **kw: None)
        tuf_repository._store = pretend.call_recorder(lambda *a, **kw: None)
        result = tuf_repository.initialize(top_roles_payload, store=True)

        assert sorted(list(result.keys())) == sorted(list(TOP_LEVEL_ROLE_NAMES))

        for call_store in tuf_repository._store.calls:
            assert call_store.args[0] in TOP_LEVEL_ROLE_NAMES

        for role in TOP_LEVEL_ROLE_NAMES:
            assert pretend.call(role) in tuf_repository.load_role.calls

    def test_initialization_store_false(self, tuf_repository):
        fake_key = {
            "keytype": "ed25519",
            "scheme": "ed25519",
            "keyid": (
                "6dcd53f0a90fca17700f819e939a74b133aa5cd8619f3dc03228c0c68dcc2abb"
            ),
            "keyid_hash_algorithms": ["sha256", "sha512"],
            "keyval": {
                "public": (
                    "c864d93b521d5851275a7b7c79fb0ac76311c206262eabd67319eba6665b1417"
                ),
                "private": (
                    "bbe40143bfe1a3b6a41647f590e398fb8dd38fddf6b279edefdc022cdb649cdc"
                ),
            },
        }
        top_roles_payload = dict()
        for role in TOP_LEVEL_ROLE_NAMES:
            top_roles_payload[role] = repository.RolesPayload(
                expiration=datetime.datetime(2019, 6, 16, 9, 5, 1),
                threshold=1,
                keys=[fake_key],
            )

        tuf_repository.load_role = pretend.call_recorder(lambda *a, **kw: None)
        tuf_repository._store = pretend.call_recorder(lambda *a, **kw: None)
        result = tuf_repository.initialize(top_roles_payload, store=False)

        assert sorted(list(result.keys())) == sorted(list(TOP_LEVEL_ROLE_NAMES))

        for call_store in tuf_repository._store.calls:
            assert call_store.args[0] in TOP_LEVEL_ROLE_NAMES

        for role in TOP_LEVEL_ROLE_NAMES:
            assert pretend.call(role) in tuf_repository.load_role.calls

    def test_initialization_already_initialized(self, tuf_repository):
        top_roles_payload = dict()
        for role in TOP_LEVEL_ROLE_NAMES:
            top_roles_payload[role] = repository.RolesPayload(
                expiration=datetime.datetime(2019, 6, 16, 9, 5, 1),
                threshold=1,
                keys=[{"key1": "key1_data"}],
            )
        tuf_repository.load_role = pretend.call_recorder(lambda *a, **kw: True)
        with pytest.raises(FileExistsError) as err:
            tuf_repository.initialize(top_roles_payload, store=False)

        assert "Metadata already exists in the Storage Service" in str(err.value)
        assert tuf_repository.load_role.calls in [
            [pretend.call("targets")],
            [pretend.call("root")],
            [pretend.call("snapshot")],
            [pretend.call("timestamp")],
        ]

    def test_initialization_threshold_more_than_keys(self, tuf_repository):
        fake_key = {
            "keytype": "ed25519",
            "scheme": "ed25519",
            "keyid": (
                "6dcd53f0a90fca17700f819e939a74b133aa5cd8619f3dc03228c0c68dcc2abb"
            ),
            "keyid_hash_algorithms": ["sha256", "sha512"],
            "keyval": {
                "public": (
                    "c864d93b521d5851275a7b7c79fb0ac76311c206262eabd67319eba6665b1417"
                ),
                "private": (
                    "bbe40143bfe1a3b6a41647f590e398fb8dd38fddf6b279edefdc022cdb649cdc"
                ),
            },
        }
        top_roles_payload = dict()
        for role in TOP_LEVEL_ROLE_NAMES:
            top_roles_payload[role] = repository.RolesPayload(
                expiration=datetime.datetime(2019, 6, 16, 9, 5, 1),
                threshold=2,
                keys=[fake_key],
            )

        tuf_repository.load_role = pretend.call_recorder(lambda *a, **kw: None)
        tuf_repository._store = pretend.call_recorder(lambda *a, **kw: None)

        with pytest.raises(ValueError) as err:
            tuf_repository.initialize(top_roles_payload, store=True)

        assert ("has missing Key(s) to match to defined threshold 2.") in str(err.value)

        for role in TOP_LEVEL_ROLE_NAMES:
            assert pretend.call(role) in tuf_repository.load_role.calls

    def test_load_role(self, tuf_repository, monkeypatch):
        fake_metadata = pretend.stub(
            from_file=pretend.call_recorder(lambda *a, **kw: None),
        )
        monkeypatch.setattr("warehouse.tuf.repository.Metadata", fake_metadata)

        tuf_repository.load_role("test_role_name")
        assert fake_metadata.from_file.calls == [
            pretend.call("test_role_name", None, tuf_repository.storage_backend)
        ]

    def test_delegate_targets_roles(self, tuf_repository):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_key = {
            "keytype": "ed25519",
            "scheme": "ed25519",
            "keyid": (
                "6dcd53f0a90fca17700f819e939a74b133aa5cd8619f3dc03228c0c68dcc2abb"
            ),
            "keyid_hash_algorithms": ["sha256", "sha512"],
            "keyval": {
                "public": (
                    "c864d93b521d5851275a7b7c79fb0ac76311c206262eabd67319eba6665b1417"
                ),
                "private": (
                    "bbe40143bfe1a3b6a41647f590e398fb8dd38fddf6b279edefdc022cdb649cdc"
                ),
            },
        }
        payload = {
            "xxxx-yyyy": [
                repository.RolesPayload(
                    expiration=fake_time,
                    threshold=1,
                    keys=[fake_key],
                    delegation_role="targets",
                    paths=["*/*"],
                )
            ]
        }
        fake_targets_md = pretend.stub(
            signed=pretend.stub(
                delegations=None,
                add_key=pretend.call_recorder(lambda *a, **kw: None),
                expires=fake_time,
                version=2,
            )
        )
        fake_snapshot_md = pretend.stub(signed=pretend.stub(meta={}))

        tuf_repository.load_role = pretend.call_recorder(
            lambda role: fake_snapshot_md if role == Snapshot.type else fake_targets_md
        )
        tuf_repository._create_delegated_targets_roles = pretend.call_recorder(
            lambda *a, **kw: fake_snapshot_md
        )
        tuf_repository.bump_role_version = pretend.call_recorder(
            lambda *a, **kw: fake_targets_md
        )
        tuf_repository.snapshot_update_meta = pretend.call_recorder(
            lambda *a, **kw: fake_snapshot_md
        )
        result = tuf_repository.delegate_targets_roles(payload)
        assert result == fake_snapshot_md
        assert tuf_repository.load_role.calls == [
            pretend.call("snapshot"),
            pretend.call("xxxx-yyyy"),
        ]
        assert tuf_repository._create_delegated_targets_roles.calls == [
            pretend.call(fake_targets_md, payload["xxxx-yyyy"], fake_snapshot_md)
        ]
        assert tuf_repository.bump_role_version.calls == [
            pretend.call(
                rolename="xxxx-yyyy",
                role_metadata=fake_targets_md,
                role_expires=fake_time,
                key_rolename=None,
                store=True,
            )
        ]
        assert tuf_repository.snapshot_update_meta.calls == [
            pretend.call("xxxx-yyyy", 2, fake_snapshot_md)
        ]

    def test_bump_role_version(self, tuf_repository):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_new_time = datetime.datetime(2022, 6, 16, 9, 5, 1)
        initial_version = 1983
        fake_role_metadata = pretend.stub(
            signed=pretend.stub(expires=fake_time, version=initial_version),
            sign=lambda *a, **kw: None,
        )

        tuf_repository.key_backend = pretend.stub(
            get=pretend.call_recorder(lambda role: [{"key": "key_data"}])
        )

        result = tuf_repository.bump_role_version(
            "fake_role", fake_role_metadata, fake_new_time
        )
        assert result.signed.version == initial_version + 1
        assert result.signed.expires == fake_new_time
        assert tuf_repository.key_backend.get.calls == [pretend.call("fake_role")]

    def test_bump_role_version_store_true(self, tuf_repository):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_new_time = datetime.datetime(2022, 6, 16, 9, 5, 1)
        initial_version = 1983
        fake_role_metadata = pretend.stub(
            signed=pretend.stub(expires=fake_time, version=initial_version),
            sign=lambda *a, **kw: None,
        )

        tuf_repository.key_backend = pretend.stub(
            get=pretend.call_recorder(lambda role: [{"key": "key_data"}])
        )
        tuf_repository._store = pretend.call_recorder(lambda rolename, role_md: None)
        result = tuf_repository.bump_role_version(
            "fake_role", fake_role_metadata, fake_new_time, store=True
        )
        assert result.signed.version == initial_version + 1
        assert result.signed.expires == fake_new_time
        assert tuf_repository.key_backend.get.calls == [pretend.call("fake_role")]
        assert tuf_repository._store.calls == [
            pretend.call("fake_role", fake_role_metadata)
        ]

    def test_bump_role_version_with_key_rolename(self, tuf_repository):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_new_time = datetime.datetime(2022, 6, 16, 9, 5, 1)
        initial_version = 1983
        fake_role_metadata = pretend.stub(
            signed=pretend.stub(expires=fake_time, version=initial_version),
            sign=lambda *a, **kw: None,
        )

        tuf_repository.key_backend = pretend.stub(
            get=pretend.call_recorder(lambda role: [{"key": "key_data"}])
        )

        result = tuf_repository.bump_role_version(
            "fake_role", fake_role_metadata, fake_new_time, "key_role_name"
        )
        assert result.signed.version == initial_version + 1
        assert result.signed.expires == fake_new_time
        assert tuf_repository.key_backend.get.calls == [pretend.call("key_role_name")]

    def test_bump_timestamp_version(self, tuf_repository):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_new_time = datetime.datetime(2022, 6, 16, 9, 5, 1)
        initial_version = 10
        fake_timestamp_md = pretend.stub(
            signed=pretend.stub(
                expires=fake_time, version=initial_version, snapshot_meta=1
            ),
            sign=lambda *a, **kw: None,
        )

        tuf_repository.load_role = pretend.call_recorder(lambda role: fake_timestamp_md)
        tuf_repository.key_backend = pretend.stub(
            get=pretend.call_recorder(lambda role: [{"key": "key_data"}])
        )

        result = tuf_repository.timestamp_bump_version(
            snapshot_version=20, timestamp_expires=fake_new_time
        )
        assert result.signed.version == initial_version + 1
        assert result.signed.expires == fake_new_time
        assert tuf_repository.load_role.calls == [pretend.call("timestamp")]
        assert tuf_repository.key_backend.get.calls == [pretend.call("timestamp")]

    def test_bump_timestamp_version_store_true(self, tuf_repository):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_new_time = datetime.datetime(2022, 6, 16, 9, 5, 1)
        initial_version = 10
        fake_timestamp_md = pretend.stub(
            signed=pretend.stub(
                expires=fake_time, version=initial_version, snapshot_meta=1
            ),
            sign=lambda *a, **kw: None,
        )

        tuf_repository.load_role = pretend.call_recorder(lambda role: fake_timestamp_md)
        tuf_repository.key_backend = pretend.stub(
            get=pretend.call_recorder(lambda role: [{"key": "key_data"}])
        )
        tuf_repository._store = pretend.call_recorder(lambda role, role_md: None)

        result = tuf_repository.timestamp_bump_version(
            snapshot_version=20, timestamp_expires=fake_new_time, store=True
        )
        assert result.signed.version == initial_version + 1
        assert result.signed.expires == fake_new_time
        assert result.signed.snapshot_meta.version == 20
        assert tuf_repository.load_role.calls == [pretend.call("timestamp")]
        assert tuf_repository.key_backend.get.calls == [pretend.call("timestamp")]
        assert tuf_repository._store.calls == [
            pretend.call("timestamp", fake_timestamp_md)
        ]

    def test_bump_snapshot_version(self, tuf_repository):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_new_time = datetime.datetime(2022, 6, 16, 9, 5, 1)
        initial_version = 10
        fake_snapshot_md = pretend.stub(
            signed=pretend.stub(
                expires=fake_time, version=initial_version, snapshot_meta=1
            ),
            sign=lambda *a, **kw: None,
        )

        tuf_repository.load_role = pretend.call_recorder(lambda role: fake_snapshot_md)
        tuf_repository.key_backend = pretend.stub(
            get=pretend.call_recorder(lambda role: [{"key": "key_data"}])
        )

        result = tuf_repository.snapshot_bump_version(fake_new_time)
        assert result.signed.version == initial_version + 1
        assert result.signed.expires == fake_new_time
        assert tuf_repository.load_role.calls == [pretend.call("snapshot")]
        assert tuf_repository.key_backend.get.calls == [pretend.call("snapshot")]

    def test_bump_snapshot_version_store_true(self, tuf_repository):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_new_time = datetime.datetime(2022, 6, 16, 9, 5, 1)
        initial_version = 10
        fake_snapshot_md = pretend.stub(
            signed=pretend.stub(
                expires=fake_time, version=initial_version, snapshot_meta=1
            ),
            sign=lambda *a, **kw: None,
        )

        tuf_repository.load_role = pretend.call_recorder(lambda role: fake_snapshot_md)
        tuf_repository.key_backend = pretend.stub(
            get=pretend.call_recorder(lambda role: [{"key": "key_data"}])
        )
        tuf_repository._store = pretend.call_recorder(lambda role, role_md: None)

        result = tuf_repository.snapshot_bump_version(fake_new_time, store=True)
        assert result.signed.version == initial_version + 1
        assert result.signed.expires == fake_new_time
        assert tuf_repository.load_role.calls == [pretend.call("snapshot")]
        assert tuf_repository.key_backend.get.calls == [pretend.call("snapshot")]
        assert tuf_repository._store.calls == [
            pretend.call("snapshot", fake_snapshot_md)
        ]

    def test_bump_snapshot_version_with_snapshot_metadata(self, tuf_repository):
        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_new_time = datetime.datetime(2022, 6, 16, 9, 5, 1)
        initial_version = 10
        fake_snapshot_md = pretend.stub(
            signed=pretend.stub(
                expires=fake_time, version=initial_version, snapshot_meta=1
            ),
            sign=lambda *a, **kw: None,
        )

        tuf_repository.key_backend = pretend.stub(
            get=pretend.call_recorder(lambda role: [{"key": "key_data"}])
        )

        result = tuf_repository.snapshot_bump_version(fake_new_time, fake_snapshot_md)
        assert result.signed.version == initial_version + 1
        assert result.signed.expires == fake_new_time
        assert tuf_repository.key_backend.get.calls == [pretend.call("snapshot")]

    def test_snapshot_update_meta(self, tuf_repository):

        fake_snapshot_md = pretend.stub(
            signed=pretend.stub(meta={"fake_role.json": MetaFile(version=2)}),
            sign=lambda *a, **kw: None,
        )

        tuf_repository.load_role = pretend.call_recorder(lambda role: fake_snapshot_md)

        result = tuf_repository.snapshot_update_meta("fake_role", 3)

        assert result.signed.meta["fake_role.json"].version == 3
        assert tuf_repository.load_role.calls == [pretend.call("snapshot")]

    def test_add_targets(self, tuf_repository):

        payload = {
            "a0-07": [
                repository.TargetsPayload(
                    fileinfo={
                        "hashes": {"blake2b-256": "sdfaslkajsdfkjhadsljkhfsdjkh"},
                        "length": 1024,
                        "custom": {"backsigned": True},
                    },
                    path="/sd/fa/lkajsdfkjhadsljkhfsdjkh.packagexv1.tar.gz",
                ),
                repository.TargetsPayload(
                    fileinfo={
                        "hashes": {"blake2b-256": "dlskjflkdjflsdjfsdfdfsdfsdfs"},
                        "length": 1025,
                        "custom": {"backsigned": True},
                    },
                    path="/sd/fa/dlskjflkdjflsdjfsdfdfsdfsdfs.packageyv1.tar.gz",
                ),
            ]
        }

        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        initial_version = 5

        fake_snapshot_md = pretend.stub(
            signed=pretend.stub(
                expires=fake_time, version=initial_version, snapshot_meta=1
            ),
            sign=lambda *a, **kw: None,
        )
        fake_role_metadata = pretend.stub(
            signed=pretend.stub(targets={}, version=initial_version, expires=fake_time),
            sign=lambda *a, **kw: None,
        )

        tuf_repository.load_role = pretend.call_recorder(
            lambda role: fake_snapshot_md
            if role == Snapshot.type
            else fake_role_metadata
        )
        tuf_repository.key_backend = pretend.stub(
            get=pretend.call_recorder(lambda role: [{"key": "key_data"}])
        )
        tuf_repository._store = pretend.call_recorder(lambda role, role_md: None)
        tuf_repository.bump_role_version = pretend.call_recorder(
            lambda *a, **kw: fake_role_metadata
        )
        tuf_repository.snapshot_update_meta = pretend.call_recorder(
            lambda *a, **kw: fake_snapshot_md
        )

        result = tuf_repository.add_targets(payload, "bins")
        assert result == fake_snapshot_md
        assert fake_role_metadata.signed.version == initial_version + 1
        assert tuf_repository.load_role.calls == [
            pretend.call("snapshot"),
            pretend.call("a0-07"),
        ]
        assert tuf_repository.key_backend.get.calls == [pretend.call("bins")]
        assert tuf_repository._store.calls == [
            pretend.call("a0-07", fake_role_metadata)
        ]
        assert tuf_repository.snapshot_update_meta.calls == [
            pretend.call("a0-07", initial_version + 1, fake_snapshot_md)
        ]
