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

from unittest import mock

import pretend
import pytest
import transaction

from celery import Celery, Task
from celery.exceptions import MaxRetriesExceededError
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

    def test_call(self, monkeypatch):
        request = pretend.stub()
        registry = pretend.stub()
        result = pretend.stub()

        prepared = {
            "registry": registry,
            "request": request,
            "closer": pretend.call_recorder(lambda: None),
        }
        prepare = pretend.call_recorder(lambda *a, **kw: prepared)
        monkeypatch.setattr(scripting, "prepare", prepare)

        @pretend.call_recorder
        def runner(irequest):
            assert irequest is request
            return result

        task = tasks.WarehouseTask()
        task.app = Celery()
        task.app.pyramid_config = pretend.stub(registry=registry)
        task.run = runner

        assert task() is result
        assert prepare.calls == [pretend.call(registry=registry)]
        assert runner.calls == [pretend.call(request)]

    def test_without_request(self, monkeypatch):
        async_result = pretend.stub()
        apply_async = pretend.call_recorder(lambda *a, **kw: async_result)

        get_current_request = pretend.call_recorder(lambda: None)
        monkeypatch.setattr(tasks, "get_current_request", get_current_request)

        task = tasks.WarehouseTask()
        task.app = Celery()

        monkeypatch.setattr(Task, "apply_async", apply_async)

        assert task.apply_async() is async_result

        assert apply_async.calls == [pretend.call(task)]
        assert get_current_request.calls == [pretend.call()]

    def test_request_without_tm(self, monkeypatch):
        async_result = pretend.stub()
        apply_async = pretend.call_recorder(lambda *a, **kw: async_result)

        request = pretend.stub()
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(tasks, "get_current_request", get_current_request)

        task = tasks.WarehouseTask()
        task.app = Celery()

        monkeypatch.setattr(Task, "apply_async", apply_async)

        assert task.apply_async() is async_result

        assert apply_async.calls == [pretend.call(task)]
        assert get_current_request.calls == [pretend.call()]

    def test_request_after_commit(self, monkeypatch):
        manager = pretend.stub(
            addAfterCommitHook=pretend.call_recorder(lambda *a, **kw: None)
        )
        request = pretend.stub(
            tm=pretend.stub(get=pretend.call_recorder(lambda: manager))
        )
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(tasks, "get_current_request", get_current_request)

        task = tasks.WarehouseTask()
        task.app = Celery()

        args = (pretend.stub(), pretend.stub())
        kwargs = {"foo": pretend.stub()}

        assert task.apply_async(*args, **kwargs) is None
        assert get_current_request.calls == [pretend.call()]
        assert request.tm.get.calls == [pretend.call()]
        assert manager.addAfterCommitHook.calls == [
            pretend.call(task._after_commit_hook, args=args, kws=kwargs)
        ]

    @pytest.mark.parametrize("success", [True, False])
    def test_after_commit_hook(self, monkeypatch, success):
        args = [pretend.stub(), pretend.stub()]
        kwargs = {"foo": pretend.stub(), "bar": pretend.stub()}

        apply_async = pretend.call_recorder(lambda *a, **kw: None)

        task = tasks.WarehouseTask()
        task.app = Celery()

        monkeypatch.setattr(Task, "apply_async", apply_async)

        task._after_commit_hook(success, *args, **kwargs)

        if success:
            assert apply_async.calls == [pretend.call(task, *args, **kwargs)]
        else:
            assert apply_async.calls == []

    def test_on_failure(self, monkeypatch):
        task = tasks.WarehouseTask()
        task.app = Celery()

        logger = pretend.stub(error=pretend.call_recorder(lambda *a, **kw: None))
        monkeypatch.setattr(tasks, "logger", logger)

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            raise (MaxRetriesExceededError)

        task.on_failure(
            MaxRetriesExceededError, "1234", pretend.stub(), pretend.stub(), exc_info
        )

        assert logger.error.calls == [
            pretend.call("Task id 1234 failed.", exc_info=exc_info)
        ]

    def test_creates_request(self, monkeypatch):
        registry = pretend.stub()
        pyramid_env = {"request": pretend.stub()}

        monkeypatch.setattr(scripting, "prepare", lambda *a, **k: pyramid_env)

        obj = tasks.WarehouseTask()
        obj.app.pyramid_config = pretend.stub(registry=registry)

        request = obj.get_request()

        assert obj.request.pyramid_env == pyramid_env
        assert request is pyramid_env["request"]
        assert isinstance(request.tm, transaction.TransactionManager)

    def test_reuses_request(self):
        pyramid_env = {"request": pretend.stub()}

        obj = tasks.WarehouseTask()
        obj.request.update(pyramid_env=pyramid_env)

        assert obj.get_request() is pyramid_env["request"]

    def test_run_creates_transaction(self, metrics):
        result = pretend.stub()
        arg = pretend.stub()
        kwarg = pretend.stub()

        request = pretend.stub(
            tm=pretend.stub(
                __enter__=pretend.call_recorder(lambda *a, **kw: None),
                __exit__=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda *a, **kw: metrics,
        )

        @pretend.call_recorder
        def run(arg_, *, kwarg_=None):
            assert arg_ is arg
            assert kwarg_ is kwarg
            return result

        task_type = type(
            "Foo",
            (tasks.WarehouseTask,),
            {"name": "warehouse.test.task", "run": staticmethod(run)},
        )

        obj = task_type()
        obj.get_request = lambda: request

        assert obj.run(arg, kwarg_=kwarg) is result
        assert run.calls == [pretend.call(arg, kwarg_=kwarg)]
        assert request.tm.__enter__.calls == [pretend.call()]
        assert request.tm.__exit__.calls == [pretend.call(None, None, None)]
        assert metrics.timed.calls == [
            pretend.call("warehouse.task.run", tags=["task:warehouse.test.task"])
        ]
        assert metrics.increment.calls == [
            pretend.call("warehouse.task.complete", tags=["task:warehouse.test.task"])
        ]

    def test_run_retries_failed_transaction(self, metrics):
        class RetryThisException(RetryableException):
            pass

        class Retry(Exception):
            pass

        def run():
            raise RetryThisException

        task_type = type(
            "Foo",
            (tasks.WarehouseTask,),
            {
                "name": "warehouse.test.task",
                "run": staticmethod(run),
                "retry": lambda *a, **kw: Retry(),
            },
        )

        request = pretend.stub(
            tm=pretend.stub(
                __enter__=pretend.call_recorder(lambda *a, **kw: None),
                __exit__=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda *a, **kw: metrics,
        )

        obj = task_type()
        obj.get_request = lambda: request

        with pytest.raises(Retry):
            obj.run()

        assert request.tm.__enter__.calls == [pretend.call()]
        assert request.tm.__exit__.calls == [pretend.call(Retry, mock.ANY, mock.ANY)]
        assert metrics.timed.calls == [
            pretend.call("warehouse.task.run", tags=["task:warehouse.test.task"])
        ]
        assert metrics.increment.calls == [
            pretend.call("warehouse.task.retried", tags=["task:warehouse.test.task"])
        ]

    def test_run_doesnt_retries_failed_transaction(self, metrics):
        class DontRetryThisException(Exception):
            pass

        def run():
            raise DontRetryThisException

        task_type = type(
            "Foo",
            (tasks.WarehouseTask,),
            {"name": "warehouse.test.task", "run": staticmethod(run)},
        )

        request = pretend.stub(
            tm=pretend.stub(
                __enter__=pretend.call_recorder(lambda *a, **kw: None),
                __exit__=pretend.call_recorder(lambda *a, **kw: None),
            ),
            find_service=lambda *a, **kw: metrics,
        )

        obj = task_type()
        obj.get_request = lambda: request

        with pytest.raises(DontRetryThisException):
            obj.run()

        assert request.tm.__enter__.calls == [pretend.call()]
        assert request.tm.__exit__.calls == [
            pretend.call(DontRetryThisException, mock.ANY, mock.ANY)
        ]
        assert metrics.timed.calls == [
            pretend.call("warehouse.task.run", tags=["task:warehouse.test.task"])
        ]
        assert metrics.increment.calls == [
            pretend.call("warehouse.task.failed", tags=["task:warehouse.test.task"])
        ]

    def test_after_return_without_pyramid_env(self):
        obj = tasks.WarehouseTask()
        assert (
            obj.after_return(
                pretend.stub(),
                pretend.stub(),
                pretend.stub(),
                pretend.stub(),
                pretend.stub(),
                pretend.stub(),
            )
            is None
        )

    def test_after_return_closes_env_runs_request_callbacks(self):
        obj = tasks.WarehouseTask()
        obj.request.pyramid_env = {
            "request": pretend.stub(
                _process_finished_callbacks=pretend.call_recorder(lambda: None)
            ),
            "closer": pretend.call_recorder(lambda: None),
        }

        obj.after_return(
            pretend.stub(),
            pretend.stub(),
            pretend.stub(),
            pretend.stub(),
            pretend.stub(),
            pretend.stub(),
        )

        assert obj.request.pyramid_env["request"]._process_finished_callbacks.calls == [
            pretend.call()
        ]
        assert obj.request.pyramid_env["closer"].calls == [pretend.call()]


class TestCeleryTaskGetter:
    def test_gets_task(self):
        task_func = pretend.stub(__name__="task_func", __module__="tests.foo")
        task_obj = pretend.stub()
        celery_app = pretend.stub(
            gen_task_name=lambda func, module: module + "." + func,
            tasks={"tests.foo.task_func": task_obj},
        )
        assert tasks._get_task(celery_app, task_func) is task_obj

    def test_get_task_via_request(self):
        task_func = pretend.stub(__name__="task_func", __module__="tests.foo")
        task_obj = pretend.stub()
        celery_app = pretend.stub(
            gen_task_name=lambda func, module: module + "." + func,
            tasks={"tests.foo.task_func": task_obj},
        )

        request = pretend.stub(registry={"celery.app": celery_app})
        get_task = tasks._get_task_from_request(request)

        assert get_task(task_func) is task_obj

    def test_get_task_via_config(self):
        task_func = pretend.stub(__name__="task_func", __module__="tests.foo")
        task_obj = pretend.stub()
        celery_app = pretend.stub(
            gen_task_name=lambda func, module: module + "." + func,
            tasks={"tests.foo.task_func": task_obj},
        )

        config = pretend.stub(registry={"celery.app": celery_app})

        assert tasks._get_task_from_config(config, task_func)


def test_add_periodic_task():
    signature = pretend.stub()
    task_obj = pretend.stub(s=lambda: signature)
    celery_app = pretend.stub(
        add_periodic_task=pretend.call_recorder(lambda *a, **k: None)
    )
    actions = []
    config = pretend.stub(
        action=pretend.call_recorder(lambda d, f, order: actions.append(f)),
        registry={"celery.app": celery_app},
        task=pretend.call_recorder(lambda t: task_obj),
    )

    schedule = pretend.stub()
    func = pretend.stub()

    tasks._add_periodic_task(config, schedule, func)

    for action in actions:
        action()

    assert config.action.calls == [pretend.call(None, mock.ANY, order=100)]
    assert config.task.calls == [pretend.call(func)]
    assert celery_app.add_periodic_task.calls == [
        pretend.call(schedule, signature, args=(), kwargs=(), name=None)
    ]


def test_make_celery_app():
    celery_app = pretend.stub()
    config = pretend.stub(registry={"celery.app": celery_app})

    assert tasks._get_celery_app(config) is celery_app


@pytest.mark.parametrize(
    ("env", "ssl", "broker_url", "expected_url", "transport_options"),
    [
        (
            Environment.development,
            False,
            "amqp://guest@rabbitmq:5672//",
            "amqp://guest@rabbitmq:5672//",
            {},
        ),
        (
            Environment.production,
            True,
            "amqp://guest@rabbitmq:5672//",
            "amqp://guest@rabbitmq:5672//",
            {},
        ),
        (Environment.development, False, "sqs://", "sqs://", {}),
        (Environment.production, True, "sqs://", "sqs://", {}),
        (
            Environment.development,
            False,
            "sqs://?queue_name_prefix=warehouse",
            "sqs://",
            {"queue_name_prefix": "warehouse-"},
        ),
        (
            Environment.production,
            True,
            "sqs://?queue_name_prefix=warehouse",
            "sqs://",
            {"queue_name_prefix": "warehouse-"},
        ),
        (
            Environment.development,
            False,
            "sqs://?region=us-east-2",
            "sqs://",
            {"region": "us-east-2"},
        ),
        (
            Environment.production,
            True,
            "sqs://?region=us-east-2",
            "sqs://",
            {"region": "us-east-2"},
        ),
        (
            Environment.development,
            False,
            "sqs:///?region=us-east-2&queue_name_prefix=warehouse",
            "sqs://",
            {"region": "us-east-2", "queue_name_prefix": "warehouse-"},
        ),
        (
            Environment.production,
            True,
            "sqs:///?region=us-east-2&queue_name_prefix=warehouse",
            "sqs://",
            {"region": "us-east-2", "queue_name_prefix": "warehouse-"},
        ),
    ],
)
def test_includeme(env, ssl, broker_url, expected_url, transport_options):
    registry_dict = {}
    config = pretend.stub(
        action=pretend.call_recorder(lambda *a, **kw: None),
        add_directive=pretend.call_recorder(lambda *a, **kw: None),
        add_request_method=pretend.call_recorder(lambda *a, **kw: None),
        registry=pretend.stub(
            __getitem__=registry_dict.__getitem__,
            __setitem__=registry_dict.__setitem__,
            settings={
                "warehouse.env": env,
                "celery.broker_url": broker_url,
                "celery.result_url": pretend.stub(),
                "celery.scheduler_url": pretend.stub(),
            },
        ),
    )
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
        "task_queues": (
            Queue("default", routing_key="task.#"),
            Queue("malware", routing_key="malware.#"),
        ),
        "task_routes": {"warehouse.malware.tasks.*": {"queue": "malware"}},
        "REDBEAT_REDIS_URL": (config.registry.settings["celery.scheduler_url"]),
    }.items():
        assert app.conf[key] == value
    assert config.action.calls == [pretend.call(("celery", "finalize"), app.finalize)]
    assert config.add_directive.calls == [
        pretend.call("add_periodic_task", tasks._add_periodic_task, action_wrap=False),
        pretend.call("make_celery_app", tasks._get_celery_app, action_wrap=False),
        pretend.call("task", tasks._get_task_from_config, action_wrap=False),
    ]
    assert config.add_request_method.calls == [
        pretend.call(tasks._get_task_from_request, name="task", reify=True)
    ]
