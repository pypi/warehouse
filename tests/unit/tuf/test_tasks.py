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

import celery
import pretend
import pytest

from warehouse.tuf import tasks
from warehouse.tuf.interfaces import IRepositoryService
from warehouse.tuf.repository import TargetsPayload


class TestBumpSnapshot:
    def test_success(self, db_request, monkeypatch):

        fake_irepository = pretend.stub()
        fake_irepository.bump_snapshot = pretend.call_recorder(lambda: None)

        db_request.registry.settings["celery.scheduler_url"] = "fake_schedule"
        db_request.find_service = pretend.call_recorder(
            lambda interface: fake_irepository
        )

        class FakeRedisLock:
            def __init__(self):
                return None

            def __enter__(self):
                return None

            def __exit__(self, type, value, traceback):
                pass

        mocked_redis = pretend.stub(lock=lambda *a: FakeRedisLock())
        monkeypatch.setattr(
            "warehouse.tuf.tasks.redis.StrictRedis.from_url",
            lambda *a, **kw: mocked_redis,
        )

        task = pretend.stub()
        tasks.bump_snapshot(task, db_request)

        assert db_request.find_service.calls == [pretend.call(IRepositoryService)]


class TestBumpBinNRoles:
    def test_success(self, db_request, monkeypatch):

        fake_irepository = pretend.stub()
        fake_irepository.bump_bin_n_roles = pretend.call_recorder(lambda: None)

        db_request.registry.settings["celery.scheduler_url"] = "fake_schedule"
        db_request.find_service = pretend.call_recorder(
            lambda interface: fake_irepository
        )

        class FakeRedisLock:
            def __init__(self):
                return None

            def __enter__(self):
                return None

            def __exit__(self, type, value, traceback):
                pass

        mocked_redis = pretend.stub(lock=lambda *a: FakeRedisLock())
        monkeypatch.setattr(
            "warehouse.tuf.tasks.redis.StrictRedis.from_url",
            lambda *a, **kw: mocked_redis,
        )

        task = pretend.stub()
        tasks.bump_bin_n_roles(task, db_request)

        assert db_request.find_service.calls == [pretend.call(IRepositoryService)]


class TestInitRepository:
    def test_success(self, db_request):

        fake_irepository = pretend.stub()
        fake_irepository.init_repository = pretend.call_recorder(lambda: None)

        db_request.registry.settings["celery.scheduler_url"] = "fake_schedule"
        db_request.find_service = pretend.call_recorder(
            lambda interface: fake_irepository
        )

        task = pretend.stub()
        tasks.init_repository(task, db_request)

        assert db_request.find_service.calls == [pretend.call(IRepositoryService)]


class TestInitTargetsDelegation:
    def test_success(self, db_request, monkeypatch):

        fake_irepository = pretend.stub()
        fake_irepository.init_targets_delegation = pretend.call_recorder(lambda: None)

        db_request.registry.settings["celery.scheduler_url"] = "fake_schedule"
        db_request.find_service = pretend.call_recorder(
            lambda interface: fake_irepository
        )

        class FakeRedisLock:
            def __init__(self):
                return None

            def __enter__(self):
                return None

            def __exit__(self, type, value, traceback):
                pass

        mocked_redis = pretend.stub(lock=lambda *a: FakeRedisLock())
        monkeypatch.setattr(
            "warehouse.tuf.tasks.redis.StrictRedis.from_url",
            lambda *a, **kw: mocked_redis,
        )

        task = pretend.stub()
        tasks.init_targets_delegation(task, db_request)

        assert db_request.find_service.calls == [pretend.call(IRepositoryService)]


class TestAddHashedTargets:
    def test_success(self, db_request, monkeypatch):

        fake_irepository = pretend.stub()
        fake_irepository.add_hashed_targets = pretend.call_recorder(
            lambda *a, **kw: None
        )

        db_request.registry.settings["celery.scheduler_url"] = "fake_schedule"
        db_request.find_service = pretend.call_recorder(
            lambda interface: fake_irepository
        )

        class FakeRedisLock:
            def __init__(self):
                return None

            def __enter__(self):
                return None

            def __exit__(self, type, value, traceback):
                pass

        mocked_redis = pretend.stub(lock=lambda *a: FakeRedisLock())
        monkeypatch.setattr(
            "warehouse.tuf.tasks.redis.StrictRedis.from_url",
            lambda *a, **kw: mocked_redis,
        )

        targets = TargetsPayload("fileinfo", "file/path")

        task = pretend.stub()
        tasks.add_hashed_targets(task, db_request, targets)

        assert db_request.find_service.calls == [pretend.call(IRepositoryService)]
