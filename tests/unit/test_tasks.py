# SPDX-License-Identifier: Apache-2.0

import types

import pytest
import transaction

from celery import Celery, Task
from kombu import Queue
from pyramid import scripting
from pyramid_retry import RetryableException

from warehouse import tasks
from warehouse.config import Environment


def test_tls_redis_backend():
    backend = tasks.TLSRedisBackend(app=Celery())
    redis_url = "rediss://localhost?ssl_cert_reqs=CERT_REQUIRED"
    params = backend._params_from_url(redis_url, {})
    assert params == {
        "connection_class": backend.redis.SSLConnection,
        "host": "localhost",
        "db": 0,
        "ssl_cert_reqs": "CERT_REQUIRED",
    }


class TestWarehouseTask:
    def test_header(self):
        def header(request, thing):
            pass

        task_type = type(
            "Foo", (tasks.WarehouseTask,), {"__header__": staticmethod(header)}
        )

        obj = task_type()
        obj.__header__(object())

    def test_call(self, mocker):
        registry = types.SimpleNamespace(settings={"warehouse.ip_salt": "peppa"})
        request = types.SimpleNamespace()

        prepared = {
            "registry": registry,
            "request": request,
            "closer": mocker.stub(name="closer"),
        }
        prepare = mocker.patch.object(scripting, "prepare", return_value=prepared)

        runner = mocker.Mock(return_value=mocker.sentinel.result)

        task = tasks.WarehouseTask()
        task.app = Celery()
        task.app.pyramid_config = types.SimpleNamespace(registry=registry)
        task.run = runner

        assert task() is mocker.sentinel.result
        prepare.assert_called_once_with(registry=registry)
        runner.assert_called_once_with(request)

    def test_retry(self, mocker, pyramid_request, metrics):
        class SpecificError(Exception):
            pass

        def runner(self):
            raise self.retry(exc=SpecificError)

        mocker.patch.object(tasks, "get_current_request", return_value=pyramid_request)

        task = tasks.WarehouseTask()
        task.app = Celery()
        task.name = "warehouse.test.task"
        task.run = runner

        with pytest.raises(SpecificError):
            task.run(task)

        metrics.increment.assert_called_once_with(
            "warehouse.task.retried", tags=["task:warehouse.test.task"]
        )

    def test_without_request(self, mocker):
        apply_async = mocker.patch.object(
            Task,
            "apply_async",
            autospec=True,
            return_value=mocker.sentinel.async_result,
        )
        get_current_request = mocker.patch.object(
            tasks, "get_current_request", return_value=None
        )

        task = tasks.WarehouseTask()
        task.app = Celery()

        assert task.apply_async() is mocker.sentinel.async_result

        apply_async.assert_called_once_with(task)
        get_current_request.assert_called_once_with()

    def test_request_without_tm(self, mocker):
        request = types.SimpleNamespace()
        apply_async = mocker.patch.object(
            Task,
            "apply_async",
            autospec=True,
            return_value=mocker.sentinel.async_result,
        )
        get_current_request = mocker.patch.object(
            tasks, "get_current_request", return_value=request
        )

        task = tasks.WarehouseTask()
        task.app = Celery()

        assert task.apply_async() is mocker.sentinel.async_result

        apply_async.assert_called_once_with(task)
        get_current_request.assert_called_once_with()

    def test_request_after_commit(self, mocker):
        manager = mocker.Mock()
        request = mocker.Mock()
        request.tm.get.return_value = manager
        get_current_request = mocker.patch.object(
            tasks, "get_current_request", return_value=request
        )

        task = tasks.WarehouseTask()
        task.app = Celery()

        args = (mocker.sentinel.arg0, mocker.sentinel.arg1)
        kwargs = {"foo": mocker.sentinel.foo}

        assert task.apply_async(*args, **kwargs) is None
        get_current_request.assert_called_once_with()
        request.tm.get.assert_called_once_with()
        manager.addAfterCommitHook.assert_called_once_with(
            task._after_commit_hook, args=args, kws=kwargs
        )

    @pytest.mark.parametrize("success", [True, False])
    def test_after_commit_hook(self, mocker, success):
        args = [mocker.sentinel.arg0, mocker.sentinel.arg1]
        kwargs = {"foo": mocker.sentinel.foo, "bar": mocker.sentinel.bar}

        apply_async = mocker.patch.object(
            Task, "apply_async", autospec=True, return_value=None
        )

        task = tasks.WarehouseTask()
        task.app = Celery()

        task._after_commit_hook(success, *args, **kwargs)

        if success:
            apply_async.assert_called_once_with(task, *args, **kwargs)
        else:
            apply_async.assert_not_called()

    def test_creates_request(self, mocker):
        registry = types.SimpleNamespace(settings={"warehouse.ip_salt": "peppa"})
        pyramid_env = {"request": types.SimpleNamespace()}

        mocker.patch.object(scripting, "prepare", return_value=pyramid_env)

        obj = tasks.WarehouseTask()
        obj.app.pyramid_config = types.SimpleNamespace(registry=registry)

        request = obj.get_request()

        assert obj.request.pyramid_env == pyramid_env
        assert request is pyramid_env["request"]
        assert isinstance(request.tm, transaction.TransactionManager)
        assert 1.5e12 < request.timings["new_request_start"] < 1e13
        assert request.remote_addr == "127.0.0.1"
        assert (
            request.remote_addr_hashed
            == "cc9dfe9c4e6b6579bbf789d04339bd2d7f10aadf84ff4394193d99f14a0333f0"
        )

    def test_reuses_request(self, mocker):
        pyramid_env = {"request": mocker.sentinel.request}

        obj = tasks.WarehouseTask()
        obj.request_stack = types.SimpleNamespace(top=None)
        obj.request.update(pyramid_env=pyramid_env)

        assert obj.get_request() is mocker.sentinel.request

    def test_run_creates_transaction(self, mocker, metrics):
        request = types.SimpleNamespace(
            tm=mocker.MagicMock(),
            find_service=lambda *a, **kw: metrics,
        )

        run = mocker.Mock(return_value=mocker.sentinel.result)

        task_type = type(
            "Foo",
            (tasks.WarehouseTask,),
            {"name": "warehouse.test.task", "run": staticmethod(run)},
        )

        obj = task_type()
        obj.get_request = lambda: request

        assert obj.run(mocker.sentinel.arg, kwarg_=mocker.sentinel.kwarg) is (
            mocker.sentinel.result
        )
        run.assert_called_once_with(mocker.sentinel.arg, kwarg_=mocker.sentinel.kwarg)
        request.tm.__enter__.assert_called_once_with()
        request.tm.__exit__.assert_called_once_with(None, None, None)
        metrics.timed.assert_called_once_with(
            "warehouse.task.run", tags=["task:warehouse.test.task"]
        )
        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.task.start", tags=["task:warehouse.test.task"]),
            mocker.call("warehouse.task.complete", tags=["task:warehouse.test.task"]),
        ]

    def test_run_retries_failed_transaction(self, mocker, metrics):
        class RetryThisError(RetryableException):
            pass

        class RetryError(Exception):
            pass

        def run():
            raise RetryThisError

        task_type = type(
            "Foo",
            (tasks.WarehouseTask,),
            {
                "name": "warehouse.test.task",
                "run": staticmethod(run),
                "retry": lambda *a, **kw: RetryError(),
            },
        )

        request = types.SimpleNamespace(
            tm=mocker.MagicMock(),
            find_service=lambda *a, **kw: metrics,
        )

        obj = task_type()
        obj.get_request = lambda: request

        with pytest.raises(RetryError):
            obj.run()

        request.tm.__enter__.assert_called_once_with()
        request.tm.__exit__.assert_called_once_with(RetryError, mocker.ANY, mocker.ANY)
        metrics.timed.assert_called_once_with(
            "warehouse.task.run", tags=["task:warehouse.test.task"]
        )
        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.task.start", tags=["task:warehouse.test.task"]),
            mocker.call("warehouse.task.retried", tags=["task:warehouse.test.task"]),
        ]

    def test_run_doesnt_retries_failed_transaction(self, mocker, metrics):
        class DontRetryThisError(Exception):
            pass

        def run():
            raise DontRetryThisError

        task_type = type(
            "Foo",
            (tasks.WarehouseTask,),
            {"name": "warehouse.test.task", "run": staticmethod(run)},
        )

        request = types.SimpleNamespace(
            tm=mocker.MagicMock(),
            find_service=lambda *a, **kw: metrics,
        )

        obj = task_type()
        obj.get_request = lambda: request

        with pytest.raises(DontRetryThisError):
            obj.run()

        request.tm.__enter__.assert_called_once_with()
        request.tm.__exit__.assert_called_once_with(
            DontRetryThisError, mocker.ANY, mocker.ANY
        )
        metrics.timed.assert_called_once_with(
            "warehouse.task.run", tags=["task:warehouse.test.task"]
        )
        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.task.start", tags=["task:warehouse.test.task"]),
            mocker.call("warehouse.task.failed", tags=["task:warehouse.test.task"]),
        ]

    def test_after_return_without_pyramid_env(self, mocker):
        obj = tasks.WarehouseTask()
        obj.request_stack = types.SimpleNamespace(top=None)
        assert (
            obj.after_return(
                mocker.sentinel.status,
                mocker.sentinel.retval,
                mocker.sentinel.task_id,
                mocker.sentinel.args,
                mocker.sentinel.kwargs,
                mocker.sentinel.einfo,
            )
            is None
        )

    def test_after_return_closes_env_runs_request_callbacks(self, mocker):
        obj = tasks.WarehouseTask()
        obj.request_stack = types.SimpleNamespace(top=None)
        inner_request = mocker.Mock()
        closer = mocker.Mock()
        obj.request.pyramid_env = {"request": inner_request, "closer": closer}

        obj.after_return(
            mocker.sentinel.status,
            mocker.sentinel.retval,
            mocker.sentinel.task_id,
            mocker.sentinel.args,
            mocker.sentinel.kwargs,
            mocker.sentinel.einfo,
        )

        inner_request._process_finished_callbacks.assert_called_once_with()
        closer.assert_called_once_with()


class TestCeleryTaskGetter:
    def test_gets_task(self, mocker):
        task_func = types.SimpleNamespace(__name__="task_func", __module__="tests.foo")
        celery_app = types.SimpleNamespace(
            gen_task_name=lambda func, module: module + "." + func,
            tasks={"tests.foo.task_func": mocker.sentinel.task_obj},
        )
        assert tasks._get_task(celery_app, task_func) is mocker.sentinel.task_obj

    def test_get_task_via_request(self, mocker):
        task_func = types.SimpleNamespace(__name__="task_func", __module__="tests.foo")
        celery_app = types.SimpleNamespace(
            gen_task_name=lambda func, module: module + "." + func,
            tasks={"tests.foo.task_func": mocker.sentinel.task_obj},
        )

        request = types.SimpleNamespace(registry={"celery.app": celery_app})
        get_task = tasks._get_task_from_request(request)

        assert get_task(task_func) is mocker.sentinel.task_obj

    def test_get_task_via_config(self, mocker):
        task_func = types.SimpleNamespace(__name__="task_func", __module__="tests.foo")
        celery_app = types.SimpleNamespace(
            gen_task_name=lambda func, module: module + "." + func,
            tasks={"tests.foo.task_func": mocker.sentinel.task_obj},
        )

        config = types.SimpleNamespace(registry={"celery.app": celery_app})

        assert tasks._get_task_from_config(config, task_func)


def test_add_periodic_task(mocker):
    task_obj = types.SimpleNamespace(s=lambda: mocker.sentinel.signature)
    celery_app = mocker.Mock()
    actions = []
    config = mocker.Mock(spec=["action", "task", "registry"])
    config.action.side_effect = lambda d, f, order: actions.append(f)
    config.task.return_value = task_obj
    config.registry = {"celery.app": celery_app}

    tasks._add_periodic_task(config, mocker.sentinel.schedule, mocker.sentinel.func)

    for action in actions:
        action()

    config.action.assert_called_once_with(None, mocker.ANY, order=100)
    config.task.assert_called_once_with(mocker.sentinel.func)
    celery_app.add_periodic_task.assert_called_once_with(
        mocker.sentinel.schedule,
        mocker.sentinel.signature,
        args=(),
        kwargs=(),
        name=None,
    )


def test_make_celery_app(mocker):
    config = types.SimpleNamespace(registry={"celery.app": mocker.sentinel.celery_app})

    assert tasks._get_celery_app(config) is mocker.sentinel.celery_app


@pytest.mark.parametrize(
    (
        "env",
        "ssl",
        "broker_redis_url",
        "expected_url",
        "transport_options",
    ),
    [
        (
            Environment.production,
            True,
            "redis://127.0.0.1:6379/10",
            "redis://127.0.0.1:6379/10",
            {},
        ),
        (
            Environment.production,
            True,
            (
                "rediss://user:pass@redis.example.com:6379/10"
                "?socket_timeout=5&irreleveant=0"
                "&ssl_cert_reqs=required&ssl_ca_certs=/p/a/t/h/cacert.pem"
            ),
            (
                "rediss://user:pass@redis.example.com:6379/10"
                "?ssl_cert_reqs=required&ssl_ca_certs=/p/a/t/h/cacert.pem"
            ),
            {
                "socket_timeout": 5,
            },
        ),
    ],
)
def test_includeme(mocker, env, ssl, broker_redis_url, expected_url, transport_options):
    class Registry(dict):
        pass

    registry = Registry()
    registry.settings = {
        "warehouse.env": env,
        "celery.broker_redis_url": broker_redis_url,
        "celery.result_url": mocker.sentinel.result_url,
        "celery.scheduler_url": mocker.sentinel.scheduler_url,
    }
    config = mocker.Mock(
        spec=["action", "add_directive", "add_request_method", "registry"]
    )
    config.registry = registry
    tasks.includeme(config)

    app = config.registry["celery.app"]

    assert app.Task is tasks.WarehouseTask
    assert app.pyramid_config is config
    for key, value in {
        "broker_transport_options": transport_options,
        "broker_url": expected_url,
        "broker_use_ssl": ssl,
        "worker_disable_rate_limits": True,
        "task_default_queue": "default",
        "task_default_routing_key": "task.default",
        "task_serializer": "json",
        "accept_content": ["json", "msgpack"],
        "task_queue_ha_policy": "all",
        "task_queues": (Queue("default", routing_key="task.#"),),
        "task_routes": {},
        "REDBEAT_REDIS_URL": (config.registry.settings["celery.scheduler_url"]),
    }.items():
        assert app.conf[key] == value
    config.action.assert_called_once_with(("celery", "finalize"), app.finalize)
    assert config.add_directive.call_args_list == [
        mocker.call("add_periodic_task", tasks._add_periodic_task, action_wrap=False),
        mocker.call("make_celery_app", tasks._get_celery_app, action_wrap=False),
        mocker.call("task", tasks._get_task_from_config, action_wrap=False),
    ]
    config.add_request_method.assert_called_once_with(
        tasks._get_task_from_request, name="task", reify=True
    )
