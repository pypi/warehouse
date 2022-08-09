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
import os
import shutil

import pretend
import pytest

from securesystemslib.exceptions import StorageError
from zope.interface.verify import verifyClass

from warehouse.config import Environment
from warehouse.tuf import services
from warehouse.tuf.constants import BIN_N_COUNT, Role
from warehouse.tuf.interfaces import IKeyService, IRepositoryService, IStorageService


class TestLocalKeyService:
    def test_verify_service(self):
        assert verifyClass(IKeyService, services.LocalKeyService)

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(settings={"tuf.key.path": "/tuf/key/path/"})
        )
        service = services.LocalKeyService.create_service(None, request)
        assert service._key_path == "/tuf/key/path/"

    def test_basic_init(self, db_request):
        service = services.LocalKeyService("/opt/warehouse/src/dev/tufkeys", db_request)
        assert service._key_path == "/opt/warehouse/src/dev/tufkeys"

    def test_get(self, db_request, monkeypatch):
        service = services.LocalKeyService("/opt/warehouse/src/dev/tufkeys", db_request)

        expected_priv_key_dict = {
            "keytype": "ed25519",
            "scheme": "ed25519",
            "keyval": {"public": "720a9a588deefd5...4d08984e87bfc5a18f34618e438434c7"},
            "keyid": "2de4eb9afe9fb73...2235d3418bd63f4214d3ba7d23b516f23e",
            "keyid_hash_algorithms": ["sha256", "sha512"],
        }
        db_request.registry.settings["tuf.root.secret"] = "tuf.root.secret"
        monkeypatch.setattr(glob, "glob", lambda privkey_path: ["fake_root.key"])
        monkeypatch.setattr(
            "warehouse.tuf.services.import_ed25519_privatekey_from_file",
            lambda *a, **kw: expected_priv_key_dict,
        )

        root_keyid = service.get("root")

        assert root_keyid[0].key_dict == expected_priv_key_dict


class TestLocalStorageService:
    def test_verify_service(self):
        assert verifyClass(IStorageService, services.LocalStorageService)

    def test_create_service(self):
        request = pretend.stub(
            registry=pretend.stub(settings={"tuf.repo.path": "/tuf/metadata/path/"})
        )
        service = services.LocalStorageService.create_service(None, request)
        assert service._repo_path == "/tuf/metadata/path/"

    def test_basic_init(self):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")
        assert service._repo_path == "/opt/warehouse/src/dev/metadata"

    def test_get(self, monkeypatch):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")
        monkeypatch.setattr(glob, "glob", lambda *a, **kw: ["1.root.json"])

        fake_file_object = pretend.stub(
            close=pretend.call_recorder(lambda: None),
            read=pretend.call_recorder(lambda: b"fake_root_data"),
        )
        monkeypatch.setitem(
            services.__builtins__, "open", lambda *a, **kw: fake_file_object
        )

        with service.get("root") as r:
            result = r.read()

        assert result == fake_file_object.read()
        assert fake_file_object.close.calls == [pretend.call()]

    def test_get_max_version_raises_valueerror(self, monkeypatch):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")

        monkeypatch.setattr(glob, "glob", lambda *a, **kw: [])

        fake_file_object = pretend.stub(
            close=pretend.call_recorder(lambda: None),
            read=pretend.call_recorder(lambda: b"fake_root_data"),
        )
        monkeypatch.setitem(
            services.__builtins__, "open", lambda *a, **kw: fake_file_object
        )

        with service.get("root") as r:
            result = r.read()

        assert result == fake_file_object.read()
        assert fake_file_object.close.calls == [pretend.call()]

    def test_get_oserror(self, monkeypatch):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")

        monkeypatch.setattr(glob, "glob", lambda *a, **kw: ["1.root.json"])
        monkeypatch.setitem(
            services.__builtins__, "open", pretend.raiser(PermissionError)
        )

        with pytest.raises(StorageError) as err:
            with service.get("root"):
                pass

        assert "Can't open /opt/warehouse/src/dev/metadata/1.root.json" in str(
            err.value
        )

    def test_get_specific_version(self, monkeypatch):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")

        monkeypatch.setattr(
            glob, "glob", lambda *a, **kw: ["1.root.json", "2.root.json", "3.root.json"]
        )

        fake_file_object = pretend.stub(
            close=pretend.call_recorder(lambda: None),
            read=pretend.call_recorder(lambda: b"fake_data"),
        )
        monkeypatch.setitem(
            services.__builtins__, "open", lambda *a, **kw: fake_file_object
        )

        with service.get("root", version=2) as r:
            result = r.read()

        assert result == fake_file_object.read()
        assert fake_file_object.close.calls == [pretend.call()]

    def test_get_timestamp_specific(self, monkeypatch):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")

        monkeypatch.setattr(glob, "glob", lambda *a, **kw: ["timestamp.json"])

        fake_file_object = pretend.stub(
            close=pretend.call_recorder(lambda: None),
            read=pretend.call_recorder(lambda: b"fake_data"),
        )
        monkeypatch.setitem(
            services.__builtins__, "open", lambda *a, **kw: fake_file_object
        )

        with service.get(Role.TIMESTAMP.value) as r:
            result = r.read()

        assert result == fake_file_object.read()

    def test_put(self, monkeypatch):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")

        fake_file_object = pretend.stub(
            closed=True, seek=pretend.call_recorder(lambda offset: None)
        )

        fake_destination_file = pretend.stub(
            flush=pretend.call_recorder(lambda: None),
            fileno=pretend.call_recorder(lambda: None),
        )

        class FakeDestinationFile:
            def __init__(self, file, mode):
                return None

            def __enter__(self):
                return fake_destination_file

            def __exit__(self, type, value, traceback):
                pass

        monkeypatch.setitem(services.__builtins__, "open", FakeDestinationFile)
        monkeypatch.setattr(shutil, "copyfileobj", lambda *a, **kw: None)
        monkeypatch.setattr(os, "fsync", lambda *a, **kw: None)

        result = service.put(fake_file_object, "2.snapshot.json")

        assert result is None
        assert fake_file_object.seek.calls == []
        assert fake_destination_file.flush.calls == [pretend.call()]
        assert fake_destination_file.fileno.calls == [pretend.call()]

    def test_put_file_object_closed(self, monkeypatch):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")

        fake_file_object = pretend.stub(
            closed=False, seek=pretend.call_recorder(lambda offset: None)
        )

        fake_destination_file = pretend.stub(
            flush=pretend.call_recorder(lambda: None),
            fileno=pretend.call_recorder(lambda: None),
        )

        class FakeDestinationFile:
            def __init__(self, file, mode):
                return None

            def __enter__(self):
                return fake_destination_file

            def __exit__(self, type, value, traceback):
                pass

        monkeypatch.setitem(services.__builtins__, "open", FakeDestinationFile)
        monkeypatch.setattr(shutil, "copyfileobj", lambda *a, **kw: None)
        monkeypatch.setattr(os, "fsync", lambda *a, **kw: None)

        result = service.put(fake_file_object, "2.snapshot.json")

        assert result is None
        assert fake_file_object.seek.calls == [pretend.call(0)]
        assert fake_destination_file.flush.calls == [pretend.call()]
        assert fake_destination_file.fileno.calls == [pretend.call()]

    def test_put_raise_oserror(self, monkeypatch):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")

        fake_file_object = pretend.stub(
            closed=True, seek=pretend.call_recorder(lambda offset: None)
        )

        monkeypatch.setitem(
            services.__builtins__, "open", pretend.raiser(PermissionError)
        )
        monkeypatch.setattr(shutil, "copyfileobj", lambda *a, **kw: None)
        monkeypatch.setattr(os, "fsync", lambda *a, **kw: None)

        with pytest.raises(StorageError) as err:
            service.put(fake_file_object, "2.snapshot.json")

        assert "Can't write file 2.snapshot.json" in str(err.value)
        assert fake_file_object.seek.calls == []

    def test_store(self, monkeypatch):
        """store is an alias for put"""
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")

        fake_file_object = pretend.stub(
            closed=True, seek=pretend.call_recorder(lambda offset: None)
        )

        fake_destination_file = pretend.stub(
            flush=pretend.call_recorder(lambda: None),
            fileno=pretend.call_recorder(lambda: None),
        )

        class FakeDestinationFile:
            def __init__(self, file, mode):
                return None

            def __enter__(self):
                return fake_destination_file

            def __exit__(self, type, value, traceback):
                pass

        monkeypatch.setitem(services.__builtins__, "open", FakeDestinationFile)
        monkeypatch.setattr(shutil, "copyfileobj", lambda *a, **kw: None)
        monkeypatch.setattr(os, "fsync", lambda *a, **kw: None)

        result = service.store(fake_file_object, "2.snapshot.json")

        assert result is None
        assert fake_file_object.seek.calls == []
        assert fake_destination_file.flush.calls == [pretend.call()]
        assert fake_destination_file.fileno.calls == [pretend.call()]


class TestRepositoryService:
    def test_verify_service(self):
        assert verifyClass(IRepositoryService, services.RepositoryService)

    def test_basic_init(self):
        service = services.RepositoryService(
            "fake_storage", "fake_key_storage", "fake_request"
        )
        assert service._storage_backend == "fake_storage"
        assert service._key_storage_backend == "fake_key_storage"
        assert service._request == "fake_request"

    def test_create_service(self):
        fake_service = "Fake Service"
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda interface: fake_service)
        )
        service = services.RepositoryService.create_service(None, request)
        assert service._storage_backend == fake_service
        assert service._key_storage_backend == fake_service
        assert service._request == request
        assert request.find_service.calls == [
            pretend.call(IStorageService),
            pretend.call(IKeyService),
        ]

    def test__get_bit_lenght(self, db_request):
        db_request.registry.settings["warehouse.env"] = Environment.development
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()
        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        response = repository_service._get_bit_length()
        assert response == 8

    def test__get_bit_lenght_production(self, db_request):
        db_request.registry.settings["warehouse.env"] = Environment.production
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        response = repository_service._get_bit_length()
        assert response == BIN_N_COUNT

    def test__is_initialized_true(self, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        repository_service._load = pretend.call_recorder(lambda *a: services.Root())

        assert repository_service._is_initialized() is True
        assert repository_service._load.calls in [
            [pretend.call(role)] for role in services.TOP_LEVEL_ROLE_NAMES
        ]

    def test__is_initialized_false(self, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        repository_service._load = pretend.call_recorder(lambda *a: None)

        assert repository_service._is_initialized() is False
        for pretend_call in repository_service._load.calls:
            assert pretend_call in [
                pretend.call(role) for role in services.TOP_LEVEL_ROLE_NAMES
            ]

    def test__is_initialized_false_by_exception(self, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        repository_service._load = pretend.raiser(services.StorageError)

        assert repository_service._is_initialized() is False

    def test__load(self, monkeypatch, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        fake_metadata = pretend.stub(
            from_file=pretend.call_recorder(lambda *a: "Metadata")
        )
        monkeypatch.setattr("warehouse.tuf.services.Metadata", fake_metadata)

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        result = repository_service._load("root")

        assert result == "Metadata"
        assert fake_metadata.from_file.calls == [
            pretend.call("root", None, fake_storage_service)
        ]

    def test__sign(self, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub(
            get=pretend.call_recorder(lambda *a: ["signer1"])
        )

        role = pretend.stub(
            signatures=pretend.stub(clear=pretend.call_recorder(lambda: None)),
            sign=pretend.call_recorder(lambda *a, **kw: None),
        )

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        result = repository_service._sign(role, "fake_role")

        assert result is None
        assert fake_key_service.get.calls == [pretend.call("fake_role")]
        assert role.signatures.clear.calls == [pretend.call()]
        assert role.sign.calls == [pretend.call("signer1", append=True)]

    def test__persist(self, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        role = pretend.stub(
            signed=pretend.stub(version=2),
            to_file=pretend.call_recorder(lambda *a, **kw: None),
        )

        services.JSONSerializer = pretend.call_recorder(lambda: None)
        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        result = repository_service._persist(role, "root")

        assert result is None
        assert role.to_file.calls == [
            pretend.call("2.root.json", services.JSONSerializer(), fake_storage_service)
        ]
        assert services.JSONSerializer.calls == [pretend.call(), pretend.call()]

    def test__persist_timestamp(self, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        role = pretend.stub(
            signed=pretend.stub(version=2),
            to_file=pretend.call_recorder(lambda *a, **kw: None),
        )

        services.JSONSerializer = pretend.call_recorder(lambda: None)
        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        result = repository_service._persist(role, Role.TIMESTAMP.value)

        assert result is None
        assert role.to_file.calls == [
            pretend.call(
                "timestamp.json", services.JSONSerializer(), fake_storage_service
            )
        ]
        assert services.JSONSerializer.calls == [pretend.call(), pretend.call()]

    def test__bump_expiry(self, monkeypatch, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        db_request.registry.settings["warehouse.env"] = Environment.production
        test_tuf_config = {
            "tuf.root.threshold": 1,
            "tuf.root.expiry": 31536000,
            "tuf.snapshot.threshold": 1,
            "tuf.snapshot.expiry": 86400,
            "tuf.targets.threshold": 2,
            "tuf.targets.expiry": 31536000,
            "tuf.timestamp.threshold": 1,
            "tuf.timestamp.expiry": 86400,
        }
        for name, value in test_tuf_config.items():
            db_request.registry.settings[name] = value

        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_datetime = pretend.stub(now=pretend.call_recorder(lambda: fake_time))
        monkeypatch.setattr("warehouse.tuf.services.datetime", fake_datetime)

        role = pretend.stub(
            signed=pretend.stub(expires=fake_datetime),
        )

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        result = repository_service._bump_expiry(role, "root")

        assert result is None
        assert role.signed.expires == datetime.datetime(2020, 6, 15, 9, 5, 1)
        assert fake_datetime.now.calls == [pretend.call()]

    def test__bump_version(self, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        role = pretend.stub(
            signed=pretend.stub(version=2),
        )

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        result = repository_service._bump_version(role)

        assert result is None
        assert role.signed.version == 3

    def test__update_timestamp(self, monkeypatch, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )

        snapshot_version = 3
        fake_metafile = pretend.call_recorder(lambda *a, **kw: snapshot_version)
        monkeypatch.setattr("warehouse.tuf.services.MetaFile", fake_metafile)

        mocked_timestamp = pretend.stub(signed=pretend.stub(snapshot_meta=2))
        repository_service._load = pretend.call_recorder(lambda *a: mocked_timestamp)
        repository_service._bump_version = pretend.call_recorder(lambda *a: None)
        repository_service._bump_expiry = pretend.call_recorder(lambda *a: None)
        repository_service._sign = pretend.call_recorder(lambda *a: None)
        repository_service._persist = pretend.call_recorder(lambda *a: None)

        result = repository_service._update_timestamp(snapshot_version)

        assert result is None
        assert mocked_timestamp.signed.snapshot_meta == snapshot_version
        assert repository_service._load.calls == [pretend.call(Role.TIMESTAMP.value)]
        assert repository_service._bump_version.calls == [
            pretend.call(mocked_timestamp)
        ]
        assert repository_service._bump_expiry.calls == [
            pretend.call(mocked_timestamp, Role.TIMESTAMP.value)
        ]
        assert repository_service._sign.calls == [
            pretend.call(mocked_timestamp, Role.TIMESTAMP.value)
        ]
        assert repository_service._persist.calls == [
            pretend.call(mocked_timestamp, Role.TIMESTAMP.value)
        ]

    def test__update_snapshot(self, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        snapshot_version = 3
        test_target_meta = [("bins", 3), ("f", 4)]
        mocked_snapshot = pretend.stub(
            signed=pretend.stub(
                meta={},
                version=snapshot_version,
            )
        )

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        repository_service._load = pretend.call_recorder(lambda *a: mocked_snapshot)
        repository_service._bump_version = pretend.call_recorder(lambda *a: None)
        repository_service._bump_expiry = pretend.call_recorder(lambda *a: None)
        repository_service._sign = pretend.call_recorder(lambda *a: None)
        repository_service._persist = pretend.call_recorder(lambda *a: None)

        result = repository_service._update_snapshot(test_target_meta)

        assert result is snapshot_version
        assert repository_service._load.calls == [pretend.call(Role.SNAPSHOT.value)]
        assert repository_service._bump_version.calls == [pretend.call(mocked_snapshot)]
        assert repository_service._bump_expiry.calls == [
            pretend.call(mocked_snapshot, Role.SNAPSHOT.value)
        ]
        assert repository_service._sign.calls == [
            pretend.call(mocked_snapshot, Role.SNAPSHOT.value)
        ]
        assert repository_service._persist.calls == [
            pretend.call(mocked_snapshot, Role.SNAPSHOT.value)
        ]

    def test_init_dev_repository(self, db_request):
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
        fake_signers = [
            pretend.stub(
                key_dict=fake_key,
                sign=pretend.call_recorder(lambda *a: "key1"),
            ),
            pretend.stub(
                key_dict=fake_key,
                sign=pretend.call_recorder(lambda *a: "key1"),
            ),
        ]
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub(
            get=pretend.call_recorder(lambda *a: fake_signers)
        )

        db_request.registry.settings["warehouse.env"] = Environment.production
        test_tuf_config = {
            "tuf.root.threshold": 1,
            "tuf.root.expiry": 31536000,
            "tuf.snapshot.threshold": 1,
            "tuf.snapshot.expiry": 86400,
            "tuf.targets.threshold": 2,
            "tuf.targets.expiry": 31536000,
            "tuf.timestamp.threshold": 1,
            "tuf.timestamp.expiry": 86400,
        }
        for name, value in test_tuf_config.items():
            db_request.registry.settings[name] = value

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )

        repository_service._is_initialized = pretend.call_recorder(lambda: False)
        repository_service._bump_expiry = pretend.call_recorder(lambda *a: None)
        repository_service._sign = pretend.call_recorder(lambda *a: None)
        repository_service._persist = pretend.call_recorder(lambda *a: None)

        result = repository_service.init_dev_repository()
        assert result is None

    def test_init_dev_repository_already_initialized(self, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        repository_service._is_initialized = pretend.call_recorder(lambda: True)
        with pytest.raises(FileExistsError) as err:
            repository_service.init_dev_repository()

        assert "TUF Metadata Repository files already exists." in str(err)

    def test_init_targets_delegation(self, db_request):
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
        fake_signers = [
            pretend.stub(
                key_dict=fake_key,
                sign=pretend.call_recorder(lambda *a: "key1"),
            ),
            pretend.stub(
                key_dict=fake_key,
                sign=pretend.call_recorder(lambda *a: "key1"),
            ),
        ]
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub(
            get=pretend.call_recorder(lambda *a: fake_signers)
        )

        db_request.registry.settings["warehouse.env"] = Environment.development

        test_tuf_config = {
            "tuf.root.threshold": 1,
            "tuf.root.expiry": 31536000,
            "tuf.snapshot.threshold": 1,
            "tuf.snapshot.expiry": 86400,
            "tuf.targets.threshold": 2,
            "tuf.targets.expiry": 31536000,
            "tuf.timestamp.threshold": 1,
            "tuf.timestamp.expiry": 86400,
            "tuf.bins.threshold": 1,
            "tuf.bins.expiry": 31536000,
            "tuf.bin-n.threshold": 1,
            "tuf.bin-n.expiry": 604800,
        }
        for name, value in test_tuf_config.items():
            db_request.registry.settings[name] = value

        fake_targets = pretend.stub(
            signed=pretend.stub(
                delegations=None,
                roles={},
                add_key=pretend.call_recorder(lambda *a: None),
                version=3,
            )
        )
        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        repository_service._load = pretend.call_recorder(lambda *a: fake_targets)
        repository_service._bump_version = pretend.call_recorder(lambda *a: None)
        repository_service._bump_expiry = pretend.call_recorder(lambda *a: None)
        repository_service._sign = pretend.call_recorder(lambda *a: None)
        repository_service._persist = pretend.call_recorder(lambda *a: None)
        repository_service._update_timestamp = pretend.call_recorder(lambda *a: None)
        repository_service._update_snapshot = pretend.call_recorder(lambda *a: 3)

        result = repository_service.init_targets_delegation()

        assert result is None
        assert repository_service._load.calls == [pretend.call("targets")]
        assert repository_service._bump_version.calls == [pretend.call(fake_targets)]
        assert repository_service._update_snapshot.calls == [
            pretend.call([("targets", 3), ("bins", 1)])
        ]
        assert repository_service._update_timestamp.calls == [pretend.call(3)]

    def test_add_hashed_targets(self, db_request):
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
        fake_signers = [
            pretend.stub(
                key_dict=fake_key,
                sign=pretend.call_recorder(lambda *a: "key1"),
            ),
            pretend.stub(
                key_dict=fake_key,
                sign=pretend.call_recorder(lambda *a: "key1"),
            ),
        ]
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub(
            get=pretend.call_recorder(lambda *a: fake_signers)
        )

        db_request.registry.settings["warehouse.env"] = Environment.development

        test_tuf_config = {
            "tuf.bin-n.threshold": 1,
            "tuf.bin-n.expiry": 604800,
        }
        for name, value in test_tuf_config.items():
            db_request.registry.settings[name] = value

        fake_bins = pretend.stub(
            signed=pretend.stub(
                delegations=pretend.stub(
                    succinct_roles=pretend.stub(
                        get_role_for_target=pretend.call_recorder(lambda *a: "bin-n-3d")
                    )
                ),
            )
        )
        fake_bin_n = pretend.stub(signed=pretend.stub(targets={}, version=4))

        def mocked_load(role):
            if role == "bins":
                return fake_bins
            else:
                return fake_bin_n

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )

        repository_service._load = pretend.call_recorder(lambda r: mocked_load(r))
        repository_service._bump_version = pretend.call_recorder(lambda *a: None)
        repository_service._bump_expiry = pretend.call_recorder(lambda *a: None)
        repository_service._sign = pretend.call_recorder(lambda *a: None)
        repository_service._persist = pretend.call_recorder(lambda *a: None)
        repository_service._update_timestamp = pretend.call_recorder(lambda *a: None)
        repository_service._update_snapshot = pretend.call_recorder(lambda *a: 3)

        targets = [
            services.TargetFile(
                1024,
                {"blake2b-256": "fake_hash_0123456789abcdef"},
                "/xy/some_package.tar.gz",
                {"backsigned": True},
            ),
            services.TargetFile(
                1024,
                {"blake2b-256": "fake_hash_0123456789abcdef"},
                "/xy/some_package.tar.gz",
                {"backsigned": True},
            ),
        ]
        result = repository_service.add_hashed_targets(targets)

        assert result is None
        assert repository_service._load.calls == [
            pretend.call("bins"),
            pretend.call("bin-n-3d"),
        ]
        assert repository_service._bump_version.calls == [pretend.call(fake_bin_n)]
        assert repository_service._bump_expiry.calls == [
            pretend.call(fake_bin_n, "bin-n")
        ]
        assert repository_service._sign.calls == [pretend.call(fake_bin_n, "bin-n")]
        assert repository_service._sign.calls == [pretend.call(fake_bin_n, "bin-n")]
        assert repository_service._update_snapshot.calls == [
            pretend.call([("bin-n-3d", 4)])
        ]
        assert repository_service._update_timestamp.calls == [pretend.call(3)]

    def test_bump_bin_n_roles(self, db_request):

        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        fake_bins = pretend.stub(
            signed=pretend.stub(
                delegations=pretend.stub(
                    succinct_roles=pretend.stub(
                        get_roles=pretend.call_recorder(lambda: ["bin-0", "bin-f"])
                    )
                ),
            )
        )
        fake_bin_n = pretend.stub(signed=pretend.stub(targets={}, version=5))

        def mocked_load(role):
            if role == "bins":
                return fake_bins
            else:
                return fake_bin_n

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        repository_service._load = pretend.call_recorder(lambda r: mocked_load(r))
        repository_service._bump_version = pretend.call_recorder(lambda *a: None)
        repository_service._bump_expiry = pretend.call_recorder(lambda *a: None)
        repository_service._sign = pretend.call_recorder(lambda *a: None)
        repository_service._persist = pretend.call_recorder(lambda *a: None)
        repository_service._update_timestamp = pretend.call_recorder(lambda *a: None)
        repository_service._update_snapshot = pretend.call_recorder(lambda *a: 6)

        result = repository_service.bump_bin_n_roles()

        assert result is None
        assert repository_service._load.calls == [
            pretend.call("bins"),
            pretend.call("bin-0"),
            pretend.call("bin-f"),
        ]
        assert repository_service._bump_version.calls == [
            pretend.call(fake_bin_n),
            pretend.call(fake_bin_n),
        ]
        assert repository_service._bump_expiry.calls == [
            pretend.call(fake_bin_n, "bin-n"),
            pretend.call(fake_bin_n, "bin-n"),
        ]
        assert repository_service._sign.calls == [
            pretend.call(fake_bin_n, "bin-n"),
            pretend.call(fake_bin_n, "bin-n"),
        ]
        assert repository_service._sign.calls == [
            pretend.call(fake_bin_n, "bin-n"),
            pretend.call(fake_bin_n, "bin-n"),
        ]
        assert repository_service._update_snapshot.calls == [
            pretend.call([("bin-0", 5), ("bin-f", 5)])
        ]
        assert repository_service._update_timestamp.calls == [pretend.call(6)]

    def test_bump_snapshot(self, db_request):
        fake_storage_service = pretend.stub()
        fake_key_service = pretend.stub()

        repository_service = services.RepositoryService(
            fake_storage_service, fake_key_service, db_request
        )
        repository_service._update_snapshot = pretend.call_recorder(lambda *a: 41)
        repository_service._update_timestamp = pretend.call_recorder(lambda *a: None)

        result = repository_service.bump_snapshot()

        assert result is None
        assert repository_service._update_snapshot.calls == [pretend.call([])]
        assert repository_service._update_timestamp.calls == [pretend.call(41)]
