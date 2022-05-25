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
from warehouse.tuf.hash_bins import HashBins
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

        with service.get("timestamp") as r:
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

    def test_create_service(self, db_request):
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

    def test_basic_init(self):
        service = services.RepositoryService(
            "fake_storage", "fake_key_storage", "fake_request"
        )
        assert service._storage_backend == "fake_storage"
        assert service._key_storage_backend == "fake_key_storage"
        assert service._request == "fake_request"

    def test__get_hash_bins_development(self, db_request):
        fake_storage = pretend.stub()
        fake_key_storage = pretend.stub()
        db_request.registry.settings["warehouse.env"] = Environment.development
        service = services.RepositoryService(fake_storage, fake_key_storage, db_request)

        result = service._get_hash_bins()
        assert type(result) == HashBins
        assert result.number_of_bins == 32
        assert result.number_of_prefixes == 256
        assert result.bin_size == 8

    def test__get_hash_bins_production(self, db_request):
        fake_storage = pretend.stub()
        fake_key_storage = pretend.stub()
        db_request.registry.settings["warehouse.env"] = Environment.production
        service = services.RepositoryService(fake_storage, fake_key_storage, db_request)

        result = service._get_hash_bins()
        assert type(result) == HashBins
        assert result.number_of_bins == BIN_N_COUNT
        assert result.number_of_prefixes == 65536
        assert result.bin_size == 4

    def test_init_repository(self, db_request, monkeypatch):
        fake_storage = pretend.stub()
        fake_key_storage = pretend.stub(
            get=pretend.call_recorder(lambda role: "fake_key")
        )

        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_datetime = pretend.stub(now=pretend.call_recorder(lambda: fake_time))
        monkeypatch.setattr(datetime, "datetime", fake_datetime)

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

        fake_metadata_repository = pretend.stub(
            is_initialized=False,
            initialize=pretend.call_recorder(lambda *a, **kw: None),
        )
        monkeypatch.setattr(
            "warehouse.tuf.services.MetadataRepository",
            lambda *a, **kw: fake_metadata_repository,
        )

        service = services.RepositoryService(fake_storage, fake_key_storage, db_request)
        result = service.init_dev_repository()

        assert result is None
        assert fake_metadata_repository.initialize.calls == [
            pretend.call(
                {
                    "targets": "fake_key",
                    "root": "fake_key",
                    "timestamp": "fake_key",
                    "snapshot": "fake_key",
                },
                store=True,
            )
        ]
        for test_call in [
            pretend.call(Role.SNAPSHOT.value),
            pretend.call(Role.ROOT.value),
            pretend.call(Role.TARGETS.value),
            pretend.call(Role.TIMESTAMP.value),
        ]:
            assert test_call in fake_key_storage.get.calls

    def test_init_repository_already_initialized(self, db_request, monkeypatch):
        fake_storage = pretend.stub()
        fake_key_storage = pretend.stub()

        db_request.registry.settings["warehouse.env"] = Environment.production

        fake_metadata_repository = pretend.stub(
            is_initialized=True,
        )

        monkeypatch.setattr(
            "warehouse.tuf.services.MetadataRepository",
            lambda *a, **kw: fake_metadata_repository,
        )
        service = services.RepositoryService(fake_storage, fake_key_storage, db_request)

        with pytest.raises(FileExistsError) as err:
            service.init_dev_repository()

        assert "TUF Metadata Repository files already exists." in str(err.value)

    def test_init_targets_delegation(self, db_request, monkeypatch):
        fake_storage = pretend.stub()
        fake_signers = [
            pretend.stub(
                key_dict={"keyid": "fake_id"},
                sign=pretend.call_recorder(lambda *a: "key1"),
            )
        ]
        fake_key_storage = pretend.stub(
            get=pretend.call_recorder(lambda role: fake_signers)
        )

        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_datetime = pretend.stub(now=pretend.call_recorder(lambda: fake_time))
        monkeypatch.setattr(datetime, "datetime", fake_datetime)

        db_request.registry.settings["warehouse.env"] = Environment.production
        test_tuf_config = {
            "tuf.snapshot.threshold": 1,
            "tuf.snapshot.expiry": 86400,
            "tuf.targets.threshold": 2,
            "tuf.targets.expiry": 31536000,
            "tuf.bins.threshold": 1,
            "tuf.bins.expiry": 31536000,
            "tuf.bin-n.threshold": 1,
            "tuf.bin-n.expiry": 604800,
        }
        for name, value in test_tuf_config.items():
            db_request.registry.settings[name] = value

        fake_metadata_repository = pretend.stub(
            is_initialized=False,
            delegate_targets_roles=pretend.call_recorder(lambda *a: None),
            _set_expiration_for_role=pretend.call_recorder(lambda *a: fake_datetime),
        )
        monkeypatch.setattr(
            "warehouse.tuf.services.MetadataRepository",
            lambda *a, **kw: fake_metadata_repository,
        )

        service = services.RepositoryService(fake_storage, fake_key_storage, db_request)
        service.bump_snapshot = pretend.call_recorder(lambda snapshot_metadata: None)
        result = service.init_targets_delegation()

        assert result is None
        call_args = fake_metadata_repository.delegate_targets_roles.calls[0].args[0]
        assert sorted(["targets", "bins"]) == sorted(list(call_args.keys()))
        assert len(call_args["targets"]) == 1
        assert type(call_args["targets"][0][0]) == services.DelegatedRole
        assert call_args["targets"][0][1][0].key_dict == {"keyid": "fake_id"}
        assert (
            len(call_args["bins"]) == 16384
        )  # PEP458 https://peps.python.org/pep-0458/#metadata-scalability
        assert type(call_args["bins"][0][0]) == services.DelegatedRole
        assert call_args["bins"][0][1][0].key_dict == {"keyid": "fake_id"}
        # 1 target + # PEP458 https://peps.python.org/pep-0458/#metadata-scalability
        assert len(fake_metadata_repository._set_expiration_for_role.calls) == 16385

    def test_bump_snapshot(self, db_request, monkeypatch):
        fake_storage = pretend.stub()
        fake_key_storage = pretend.stub(
            get=pretend.call_recorder(lambda role: "fake_key")
        )

        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_datetime = pretend.stub(now=pretend.call_recorder(lambda: fake_time))
        monkeypatch.setattr(datetime, "datetime", fake_datetime)

        db_request.registry.settings["warehouse.env"] = Environment.production
        test_tuf_config = {
            "tuf.snapshot.expiry": 86400,
            "tuf.timestamp.expiry": 86400,
        }

        for name, value in test_tuf_config.items():
            db_request.registry.settings[name] = value

        fake_snapshot = pretend.stub(signed=pretend.stub(version=2))
        fake_metadata_repository = pretend.stub(
            load_role=pretend.call_recorder(lambda role: fake_snapshot),
            snapshot_bump_version=pretend.call_recorder(lambda *a, **kw: fake_snapshot),
            timestamp_bump_version=pretend.call_recorder(lambda *a, **kw: None),
        )
        monkeypatch.setattr(
            "warehouse.tuf.services.MetadataRepository",
            lambda *a, **kw: fake_metadata_repository,
        )

        service = services.RepositoryService(fake_storage, fake_key_storage, db_request)
        result = service.bump_snapshot()

        bump_s_calls = fake_metadata_repository.snapshot_bump_version.calls[0].kwargs
        bump_t_calls = fake_metadata_repository.timestamp_bump_version.calls[0].kwargs

        assert result is None
        assert fake_metadata_repository.load_role.calls == [pretend.call("snapshot")]
        assert bump_s_calls["snapshot_metadata"].signed.version == 2
        assert bump_s_calls["store"] is True
        assert bump_t_calls["snapshot_version"] == 2
        assert bump_t_calls["store"] is True

    def test_bump_snapshot_specific_snapshot_metadata(self, db_request, monkeypatch):
        fake_storage = pretend.stub()
        fake_key_storage = pretend.stub(
            get=pretend.call_recorder(lambda role: "fake_key")
        )

        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_datetime = pretend.stub(now=pretend.call_recorder(lambda: fake_time))
        monkeypatch.setattr(datetime, "datetime", fake_datetime)

        db_request.registry.settings["warehouse.env"] = Environment.production
        test_tuf_config = {
            "tuf.snapshot.expiry": 86400,
            "tuf.timestamp.expiry": 86400,
        }

        for name, value in test_tuf_config.items():
            db_request.registry.settings[name] = value

        fake_snapshot = pretend.stub(signed=pretend.stub(version=2))
        fake_metadata_repository = pretend.stub(
            snapshot_bump_version=pretend.call_recorder(lambda *a, **kw: fake_snapshot),
            timestamp_bump_version=pretend.call_recorder(lambda *a, **kw: None),
        )
        monkeypatch.setattr(
            "warehouse.tuf.services.MetadataRepository",
            lambda *a, **kw: fake_metadata_repository,
        )

        service = services.RepositoryService(fake_storage, fake_key_storage, db_request)
        result = service.bump_snapshot(fake_snapshot)

        bump_s_calls = fake_metadata_repository.snapshot_bump_version.calls[0].kwargs
        bump_t_calls = fake_metadata_repository.timestamp_bump_version.calls[0].kwargs

        assert result is None
        assert bump_s_calls["snapshot_metadata"].signed.version == 2
        assert bump_s_calls["store"] is True
        assert bump_t_calls["snapshot_version"] == 2
        assert bump_t_calls["store"] is True

    def test_bump_bin_n_roles(self, db_request, monkeypatch):
        fake_storage = pretend.stub()
        fake_signers = [
            pretend.stub(
                key_dict={"keyid": "fake_id"},
                sign=pretend.call_recorder(lambda *a: "key1"),
            )
        ]
        fake_key_storage = pretend.stub(
            get=pretend.call_recorder(lambda role: fake_signers)
        )

        fake_time = datetime.datetime(2019, 6, 16, 9, 5, 1)
        fake_datetime = pretend.stub(now=pretend.call_recorder(lambda: fake_time))
        monkeypatch.setattr(datetime, "datetime", fake_datetime)

        db_request.registry.settings["warehouse.env"] = Environment.production
        test_tuf_config = {
            "tuf.snapshot.expiry": 86400,
            "tuf.timestamp.expiry": 86400,
            "tuf.bin-n.expiry": 604800,
            "tuf.bins.expiry": 31536000,
        }

        for name, value in test_tuf_config.items():
            db_request.registry.settings[name] = value

        fake_bin_n_metadata = pretend.stub(signed=pretend.stub(version=5))
        fake_snapshot = pretend.stub(signed=pretend.stub(version=2))
        fake_metadata_repository = pretend.stub(
            load_role=pretend.call_recorder(
                lambda role: fake_snapshot
                if role == Role.SNAPSHOT.value
                else fake_bin_n_metadata
            ),
            bump_role_version=pretend.call_recorder(lambda *a, **kw: None),
            snapshot_bump_version=pretend.call_recorder(lambda *a, **kw: fake_snapshot),
            snapshot_update_meta=pretend.call_recorder(
                lambda *a, **kw: "snapshot_metadata"
            ),
            timestamp_bump_version=pretend.call_recorder(lambda *a, **kw: None),
            _set_expiration_for_role=pretend.call_recorder(lambda *a: fake_datetime),
            _key_storage_backend=pretend.call_recorder(lambda *a: fake_signers),
        )
        monkeypatch.setattr(
            "warehouse.tuf.services.MetadataRepository",
            lambda *a, **kw: fake_metadata_repository,
        )

        service = services.RepositoryService(fake_storage, fake_key_storage, db_request)
        service.bump_snapshot = pretend.call_recorder(lambda snapshot_metadata: None)

        result = service.bump_bin_n_roles()

        assert result is None
        # PEP458 https://peps.python.org/pep-0458/#metadata-scalability
        assert len(fake_metadata_repository.bump_role_version.calls) == 16384
        assert len(fake_metadata_repository.snapshot_update_meta.calls) == 16384
        assert (
            len(fake_metadata_repository.load_role.calls) == 16385
        )  # +1 snapshot call
        assert (
            fake_metadata_repository.load_role.calls.count(pretend.call("snapshot"))
            == 1
        )
        assert len(fake_metadata_repository._set_expiration_for_role.calls) == 16384
        assert service.bump_snapshot.calls == [pretend.call("snapshot_metadata")]

    def test_add_hashed_targets(self, db_request, monkeypatch):
        db_request.registry.settings["warehouse.env"] = Environment.production

        fake_storage = pretend.stub()
        fake_key_storage = pretend.stub()
        fake_metadata_repository = pretend.stub(
            add_targets=pretend.call_recorder(lambda *a, **kw: "snapshot_metadata"),
        )
        monkeypatch.setattr(
            "warehouse.tuf.services.MetadataRepository",
            lambda *a, **kw: fake_metadata_repository,
        )

        monkeypatch.setattr(
            "warehouse.tuf.services.TargetFile.from_dict",
            lambda *a, **kw: "target_dict",
        )

        fake_hash_bins = pretend.stub(
            get_delegate=pretend.call_recorder(lambda filepath: "xxxx-yyyy")
        )
        service = services.RepositoryService(fake_storage, fake_key_storage, db_request)
        service.bump_snapshot = pretend.call_recorder(lambda snapshot_metadata: None)
        service._get_hash_bins = pretend.call_recorder(lambda: fake_hash_bins)

        targets = [
            {
                "info": {
                    "hashes": {"blake2b-256": "sdfaslkajsdfkjhadsljkhfsdjkh"},
                    "length": 1024,
                    "custom": {"backsigned": True},
                },
                "path": "/sd/fa/lkajsdfkjhadsljkhfsdjkh.packagexv1.tar.gz",
            },
            {
                "info": {
                    "hashes": {"blake2b-256": "dlskjflkdjflsdjfsdfdfsdfsdfs"},
                    "length": 1025,
                    "custom": {"backsigned": True},
                },
                "path": "/sd/fa/dlskjflkdjflsdjfsdfdfsdfsdfs.packageyv1.tar.gz",
            },
        ]
        result = service.add_hashed_targets(targets)

        assert result is None
        assert fake_metadata_repository.add_targets.calls == [
            pretend.call(
                {"xxxx-yyyy": ["target_dict", "target_dict"]},
                "bin-n",
            )
        ], fake_metadata_repository.add_targets.calls
        assert service.bump_snapshot.calls == [pretend.call("snapshot_metadata")]
        assert service._get_hash_bins.calls == [pretend.call()]
        assert fake_hash_bins.get_delegate.calls == [
            pretend.call("/sd/fa/lkajsdfkjhadsljkhfsdjkh.packagexv1.tar.gz"),
            pretend.call("/sd/fa/dlskjflkdjflsdjfsdfdfsdfsdfs.packageyv1.tar.gz"),
        ]
