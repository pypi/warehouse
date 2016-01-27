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

import pretend
import pytest

from celery import Celery
from pyramid import scripting

from warehouse import celery
from warehouse.config import Environment


def test_configure_celery(monkeypatch):
    configure = pretend.call_recorder(lambda: None)
    monkeypatch.setattr(celery, "configure", configure)

    celery._configure_celery()

    assert configure.calls == [pretend.call()]


def test_tls_redis_backend():
    backend = celery.TLSRedisBackend(app=Celery())
    params = backend._params_from_url("rediss://localhost", {})
    assert params == {
        "connection_class": backend.redis.SSLConnection,
        "host": "localhost",
        "db": 0,
    }


class TestWarehouseTask:

    def test_call(self, monkeypatch):
        request = pretend.stub()
        registry = pretend.stub()
        result = pretend.stub()

        prepared = {
            "registry": registry,
            "request": request,
            "closer": pretend.call_recorder(lambda: None)
        }
        prepare = pretend.call_recorder(lambda *a, **kw: prepared)
        monkeypatch.setattr(scripting, "prepare", prepare)

        @pretend.call_recorder
        def runner(irequest):
            assert irequest is request
            return result

        task = celery.WarehouseTask()
        task.app = Celery()
        task.app.pyramid_config = pretend.stub(registry=registry)
        task.run = runner

        assert task() is result
        assert prepare.calls == [pretend.call(registry=registry)]
        assert prepared["closer"].calls == [pretend.call()]
        assert runner.calls == [pretend.call(request)]

    def test_without_request(self, monkeypatch):
        async_result = pretend.stub()
        super_class = pretend.stub(
            apply_async=pretend.call_recorder(lambda *a, **kw: async_result),
        )
        real_super = __builtins__["super"]
        inner_super = pretend.call_recorder(lambda *a, **kw: super_class)

        def fake_super(*args, **kwargs):
            if not args and not kwargs:
                return inner_super(*args, **kwargs)
            else:
                return real_super(*args, **kwargs)

        monkeypatch.setitem(__builtins__, "super", fake_super)

        get_current_request = pretend.call_recorder(lambda: None)
        monkeypatch.setattr(celery, "get_current_request", get_current_request)

        task = celery.WarehouseTask()
        task.app = Celery()

        assert task.apply_async() is async_result

        assert super_class.apply_async.calls == [pretend.call()]
        assert get_current_request.calls == [pretend.call()]
        assert inner_super.calls == [pretend.call()]

    def test_request_without_tm(self, monkeypatch):
        async_result = pretend.stub()
        super_class = pretend.stub(
            apply_async=pretend.call_recorder(lambda *a, **kw: async_result),
        )
        real_super = __builtins__["super"]
        inner_super = pretend.call_recorder(lambda *a, **kw: super_class)

        def fake_super(*args, **kwargs):
            if not args and not kwargs:
                return inner_super(*args, **kwargs)
            else:
                return real_super(*args, **kwargs)

        monkeypatch.setitem(__builtins__, "super", fake_super)

        request = pretend.stub()
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(celery, "get_current_request", get_current_request)

        task = celery.WarehouseTask()
        task.app = Celery()

        assert task.apply_async() is async_result

        assert super_class.apply_async.calls == [pretend.call()]
        assert get_current_request.calls == [pretend.call()]
        assert inner_super.calls == [pretend.call()]

    def test_request_after_commit(self, monkeypatch):
        manager = pretend.stub(
            addAfterCommitHook=pretend.call_recorder(lambda *a, **kw: None),
        )
        request = pretend.stub(
            tm=pretend.stub(get=pretend.call_recorder(lambda: manager)),
        )
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(celery, "get_current_request", get_current_request)

        task = celery.WarehouseTask()
        task.app = Celery()

        args = (pretend.stub(), pretend.stub())
        kwargs = {"foo": pretend.stub()}

        assert task.apply_async(*args, **kwargs) is None
        assert get_current_request.calls == [pretend.call()]
        assert request.tm.get.calls == [pretend.call()]
        assert manager.addAfterCommitHook.calls == [
            pretend.call(task._after_commit_hook, args=args, kws=kwargs),
        ]

    @pytest.mark.parametrize("success", [True, False])
    def test_after_commit_hook(self, monkeypatch, success):
        args = [pretend.stub(), pretend.stub()]
        kwargs = {"foo": pretend.stub(), "bar": pretend.stub()}

        super_class = pretend.stub(
            apply_async=pretend.call_recorder(lambda *a, **kw: None),
        )
        real_super = __builtins__["super"]
        inner_super = pretend.call_recorder(lambda *a, **kw: super_class)

        def fake_super(*args, **kwargs):
            if not args and not kwargs:
                return inner_super(*args, **kwargs)
            else:
                return real_super(*args, **kwargs)

        monkeypatch.setitem(__builtins__, "super", fake_super)

        task = celery.WarehouseTask()
        task.app = Celery()
        task._after_commit_hook(success, *args, **kwargs)

        if success:
            assert inner_super.calls == [pretend.call()]
        else:
            assert inner_super.calls == []


@pytest.mark.parametrize(
    ("env", "ssl"),
    [
        (Environment.development, False),
        (Environment.production, True),
    ],
)
def test_includeme(monkeypatch, env, ssl):
    app = pretend.stub(conf={})
    monkeypatch.setattr(celery, "app", app)

    config = pretend.stub(
        registry=pretend.stub(
            settings={
                "warehouse.env": env,
                "celery.broker_url": pretend.stub(),
                "celery.result_url": pretend.stub(),
            },
        ),
    )
    celery.includeme(config)

    assert app.pyramid_config is config
    assert app.conf == {
        "BROKER_URL": config.registry.settings["celery.broker_url"],
        "BROKER_USE_SSL": ssl,
        "CELERY_DISABLE_RATE_LIMITS": True,
        "CELERY_RESULT_BACKEND": config.registry.settings["celery.result_url"],
        "CELERY_RESULT_SERIALIZER": "json",
        "CELERY_TASK_SERIALIZER": "json",
        "CELERY_ACCEPT_CONTENT": ["json", "msgpack"],
        "CELERY_MESSAGE_COMPRESSION": "gzip",
        "CELERY_QUEUE_HA_POLICY": "all",
    }
