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
import os
import shutil

import pretend
import pytest

from securesystemslib.exceptions import StorageError
from zope.interface.verify import verifyClass

from warehouse.tuf import services
from warehouse.tuf.interfaces import IKeyService, IStorageService


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
        monkeypatch.setattr(
            "warehouse.tuf.services.import_ed25519_privatekey_from_file",
            lambda *a, **kw: expected_priv_key_dict,
        )

        root_keyid = service.get("root")

        assert root_keyid == [expected_priv_key_dict]


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
            __enter__=None,
            __exit__=None,
            close=pretend.call_recorder(lambda: None),
            read=pretend.call_recorder(lambda: b"fake_root_data"),
        )
        monkeypatch.setitem(
            services.__builtins__, "open", lambda *a, **kw: fake_file_object
        )

        with service.get("root") as r:
            result = r.read()

        assert result == b"fake_root_data"
        assert fake_file_object.close.calls == [pretend.call()]

    def test_get_max_version_raises_valueerror(self, monkeypatch):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")

        monkeypatch.setattr(glob, "glob", lambda *a, **kw: [])

        fake_file_object = pretend.stub(
            __enter__=None,
            __exit__=None,
            close=pretend.call_recorder(lambda: None),
            read=pretend.call_recorder(lambda: b"fake_root_data"),
        )
        monkeypatch.setitem(
            services.__builtins__, "open", lambda *a, **kw: fake_file_object
        )

        with service.get("root") as r:
            result = r.read()

        assert result == b"fake_root_data"
        assert fake_file_object.close.calls == [pretend.call()]

    def test_get_oserror(self, monkeypatch):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")

        monkeypatch.setattr(glob, "glob", lambda *a, **kw: ["1.root.json"])
        monkeypatch.setitem(
            services.__builtins__, "open", pretend.raiser(PermissionError)
        )

        with pytest.raises(StorageError) as err:
            with service.get("root") as r:
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
            __enter__=None,
            __exit__=None,
            close=pretend.call_recorder(lambda: None),
            read=pretend.call_recorder(lambda: b"fake_data"),
        )
        monkeypatch.setitem(
            services.__builtins__, "open", lambda *a, **kw: fake_file_object
        )

        with service.get("root", version=2) as r:
            result = r.read()

        assert result == b"fake_data"
        assert fake_file_object.close.calls == [pretend.call()]

    def test_get_timestamp_specific(self, monkeypatch):
        service = services.LocalStorageService("/opt/warehouse/src/dev/metadata")

        monkeypatch.setattr(glob, "glob", lambda *a, **kw: ["timestamp.json"])

        fake_file_object = pretend.stub(
            __enter__=None,
            __exit__=None,
            close=pretend.call_recorder(lambda: None),
            read=pretend.call_recorder(lambda: b"fake_data"),
        )
        monkeypatch.setitem(
            services.__builtins__, "open", lambda *a, **kw: fake_file_object
        )

        with service.get("timestamp") as r:
            result = r.read()

        assert result == b"fake_data"

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
