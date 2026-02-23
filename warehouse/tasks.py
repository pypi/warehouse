# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import functools
import hashlib
import logging
import time
import typing
import urllib.parse
import uuid

import celery
import celery.app.backends
import celery.backends.redis
import pyramid.scripting
import pyramid_retry
import structlog
import transaction
import venusian

from celery import signals
from kombu import Queue
from pyramid.threadlocal import get_current_request

from warehouse.config import Environment
from warehouse.logging import configure_celery_logging
from warehouse.metrics import IMetricsService

if typing.TYPE_CHECKING:
    from pyramid.config import Configurator
    from pyramid.request import Request

# We need to trick Celery into supporting rediss:// URLs which is how redis-py
# signals that you should use Redis with TLS.
celery.app.backends.BACKEND_ALIASES["rediss"] = (
    "warehouse.tasks:TLSRedisBackend"  # noqa
)


logger = logging.getLogger(__name__)


# Celery signal handlers for unified structlog configuration
@signals.after_setup_logger.connect
def on_after_setup_logger(logger, loglevel, logfile, *args, **kwargs):
    """Override Celery's default logging behavior
    with unified structlog configuration."""
    configure_celery_logging(logfile, loglevel)


@signals.task_prerun.connect
def on_task_prerun(sender, task_id, task, **_):
    """Bind task metadata to contextvars for all logs within the task."""
    structlog.contextvars.bind_contextvars(task_id=task_id, task_name=task.name)


class TLSRedisBackend(celery.backends.redis.RedisBackend):
    def _params_from_url(self, url, defaults):
        params = super()._params_from_url(url, defaults)
        params.update({"connection_class": self.redis.SSLConnection})
        return params


class WarehouseTask(celery.Task):
    """
    A custom Celery Task that integrates with Pyramid's transaction manager and
    metrics service.
    """

    __header__: typing.Callable
    _wh_original_run: typing.Callable

    def __new__(cls, *args, **kwargs) -> WarehouseTask:
        """
        Override to wrap the `run` method of the task with a new method that
        will handle exceptions from the task and retry them if they're retryable.
        """
        obj = super().__new__(cls, *args, **kwargs)
        if getattr(obj, "__header__", None) is not None:
            obj.__header__ = functools.partial(obj.__header__, object())

        # We do this here instead of inside of __call__ so that exceptions
        # coming from the transaction manager get caught by the autoretry
        # mechanism.
        @functools.wraps(obj.run)
        def run(*args, **kwargs):
            original_run = obj._wh_original_run
            request = obj.get_request()
            metrics = request.find_service(IMetricsService, context=None)
            metric_tags = [f"task:{obj.name}"]

            with request.tm, metrics.timed("warehouse.task.run", tags=metric_tags):
                metrics.increment("warehouse.task.start", tags=metric_tags)
                try:
                    result = original_run(*args, **kwargs)
                    metrics.increment("warehouse.task.complete", tags=metric_tags)
                    return result
                except BaseException as exc:
                    if isinstance(
                        exc, pyramid_retry.RetryableException
                    ) or pyramid_retry.IRetryableError.providedBy(exc):
                        metrics.increment("warehouse.task.retried", tags=metric_tags)
                        raise obj.retry(exc=exc)
                    metrics.increment("warehouse.task.failed", tags=metric_tags)
                    raise

        # Reassign the `run` method to the new one we've created.
        obj._wh_original_run, obj.run = obj.run, run  # type: ignore[method-assign]

        return obj

    def __call__(self, *args, **kwargs):
        """
        Override to inject a faux request object into the task when it's called.
        There's no WSGI request object available when a task is called, so we
        create a fake one here. This is necessary as a lot of our code assumes
        that there's a Pyramid request object available.
        """
        return super().__call__(*(self.get_request(),) + args, **kwargs)

    def get_request(self) -> Request:
        """
        Get a request object to use for this task.

        This will either return the request object that was injected into the
        task when it was called, or it will create a new request object to use
        for the task.

        Note: The `type: ignore` comments are necessary because the `pyramid_env`
        attribute is not defined on the request object, but we're adding it
        dynamically.
        """
        if not hasattr(self.request, "pyramid_env"):
            registry = self.app.pyramid_config.registry  # type: ignore[attr-defined]
            env = pyramid.scripting.prepare(registry=registry)
            env["request"].tm = transaction.TransactionManager(explicit=True)
            env["request"].timings = {"new_request_start": time.time() * 1000}
            env["request"].remote_addr = "127.0.0.1"
            env["request"].remote_addr_hashed = hashlib.sha256(
                ("127.0.0.1" + registry.settings["warehouse.ip_salt"]).encode("utf8")
            ).hexdigest()
            request_id = str(uuid.uuid4())
            env["request"].id = request_id
            structlog.contextvars.bind_contextvars(**{"request.id": request_id})
            env["request"].log = structlog.get_logger("warehouse.request")
            self.request.update(pyramid_env=env)

        return self.request.pyramid_env["request"]  # type: ignore[attr-defined]

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """
        Called after the task has returned. This is where we'll clean up the
        request object that we injected into the task.
        """
        if hasattr(self.request, "pyramid_env"):
            pyramid_env = self.request.pyramid_env
            pyramid_env["request"]._process_finished_callbacks()
            pyramid_env["closer"]()

    def apply_async(self, *args, **kwargs):
        """
        Override the apply_async method to add an after commit hook to the
        transaction manager to send the task after the transaction has been
        committed.

        This is necessary because we want to ensure that the task is only sent
        after the transaction has been committed. This is important because we
        want to ensure that the task is only sent if the transaction was
        successful.
        """
        # The API design of Celery makes this threadlocal pretty impossible to
        # avoid :(
        request = get_current_request()

        # If for whatever reason we were unable to get a request we'll just
        # skip this and call the original method to send this immediately.
        if request is None or not hasattr(request, "tm"):
            return super().apply_async(*args, **kwargs)

        # This will break things that expect to get an AsyncResult because
        # we're no longer going to be returning an async result from this when
        # called from within a request, response cycle. Ideally we shouldn't be
        # waiting for responses in a request/response cycle anyways though.
        request.tm.get().addAfterCommitHook(
            self._after_commit_hook, args=args, kws=kwargs
        )

    def retry(self, *args, **kwargs):
        """
        Override the retry method to increment a metric when a task is retried.

        This is necessary because the `retry` method is called when a task is
        retried, and we want to track how many times a task has been retried.
        """
        request = get_current_request()
        metrics = request.find_service(IMetricsService, context=None)
        metrics.increment("warehouse.task.retried", tags=[f"task:{self.name}"])
        return super().retry(*args, **kwargs)

    def _after_commit_hook(self, success, *args, **kwargs):
        """
        This is the hook that gets called after the transaction has been
        committed. We'll only send the task if the transaction was successful.
        """
        if success:
            super().apply_async(*args, **kwargs)


def task(**kwargs):
    """
    A decorator that can be used to define a Celery task.

    A thin wrapper around Celery's `task` decorator that allows us to attach
    the task to the Celery app when the configuration is scanned during the
    application startup.

    This decorator also sets the `shared` option to `False` by default. This
    means that the task will be created anew for each worker process that is
    started. This is important because the `WarehouseTask` class that we use
    for our tasks is not thread-safe, so we need to ensure that each worker
    process has its own instance of the task.

    This decorator also adds the task to the `warehouse` category in the
    configuration scanner. This is important because we use this category to
    find all the tasks that have been defined in the configuration.

    Example usage:
    ```
    @tasks.task(...)
    def my_task(self, *args, **kwargs):
        pass
    ```
    """
    kwargs.setdefault("shared", False)

    def deco(wrapped):
        def callback(scanner, name, wrapped):
            celery_app = scanner.config.registry["celery.app"]
            celery_app.task(**kwargs)(wrapped)

        venusian.attach(wrapped, callback, category="warehouse")

        return wrapped

    return deco


def _get_task(celery_app, task_func):
    task_name = celery_app.gen_task_name(task_func.__name__, task_func.__module__)
    return celery_app.tasks[task_name]


def _get_task_from_request(request):
    celery_app = request.registry["celery.app"]
    return functools.partial(_get_task, celery_app)


def _get_task_from_config(config, task):
    celery_app = config.registry["celery.app"]
    return _get_task(celery_app, task)


def _get_celery_app(config):
    return config.registry["celery.app"]


def _add_periodic_task(config, schedule, func, args=(), kwargs=(), name=None, **opts):
    def add_task():
        config.registry["celery.app"].add_periodic_task(
            schedule, config.task(func).s(), args=args, kwargs=kwargs, name=name, **opts
        )

    config.action(None, add_task, order=100)


def includeme(config: Configurator) -> None:
    s = config.registry.settings

    broker_transport_options: dict[str, str | int | dict] = {}

    broker_url = s["celery.broker_redis_url"]

    # Only redis is supported as a broker
    assert broker_url.startswith("redis")

    parsed_url = urllib.parse.urlparse(  # noqa: WH001, going to urlunparse this
        broker_url
    )
    parsed_query = urllib.parse.parse_qs(parsed_url.query)

    celery_transport_options = {
        "socket_timeout": int,
    }

    for key, value in parsed_query.copy().items():
        if key.startswith("ssl_"):
            continue
        else:
            if key in celery_transport_options:
                broker_transport_options[key] = celery_transport_options[key](value[0])
            del parsed_query[key]

    parsed_url = parsed_url._replace(
        query=urllib.parse.urlencode(parsed_query, doseq=True, safe="/")
    )
    broker_url = urllib.parse.urlunparse(parsed_url)

    config.registry["celery.app"] = celery.Celery(
        "warehouse", autofinalize=False, set_as_current=False
    )
    config.registry["celery.app"].conf.update(
        accept_content=["json", "msgpack"],
        broker_url=broker_url,
        broker_use_ssl=s["warehouse.env"] == Environment.production,
        broker_transport_options=broker_transport_options,
        task_default_queue="default",
        task_default_routing_key="task.default",
        task_queue_ha_policy="all",
        task_queues=(Queue("default", routing_key="task.#"),),
        task_routes={},
        task_serializer="json",
        worker_disable_rate_limits=True,
        REDBEAT_REDIS_URL=s["celery.scheduler_url"],
        # Silence deprecation warning on startup
        broker_connection_retry_on_startup=False,
        # Disable Celery's logger hijacking for unified structlog control
        worker_hijack_root_logger=False,
        worker_log_format="%(message)s",
        worker_task_log_format="%(message)s",
    )
    config.registry["celery.app"].Task = WarehouseTask
    config.registry["celery.app"].pyramid_config = config

    config.action(("celery", "finalize"), config.registry["celery.app"].finalize)

    config.add_directive("add_periodic_task", _add_periodic_task, action_wrap=False)
    config.add_directive("make_celery_app", _get_celery_app, action_wrap=False)
    config.add_directive("task", _get_task_from_config, action_wrap=False)
    config.add_request_method(_get_task_from_request, name="task", reify=True)
