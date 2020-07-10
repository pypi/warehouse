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

import functools
import logging
import urllib.parse

import celery
import celery.app.backends
import celery.backends.redis
import pyramid.scripting
import pyramid_retry
import transaction
import venusian

from kombu import Queue
from pyramid.threadlocal import get_current_request

from warehouse.config import Environment
from warehouse.metrics import IMetricsService

# We need to trick Celery into supporting rediss:// URLs which is how redis-py
# signals that you should use Redis with TLS.
celery.app.backends.BACKEND_ALIASES[
    "rediss"
] = "warehouse.tasks:TLSRedisBackend"  # noqa


# We need to register that the sqs:// url scheme uses a netloc
urllib.parse.uses_netloc.append("sqs")

logger = logging.getLogger(__name__)


class TLSRedisBackend(celery.backends.redis.RedisBackend):
    def _params_from_url(self, url, defaults):
        params = super()._params_from_url(url, defaults)
        params.update({"connection_class": self.redis.SSLConnection})
        return params


class WarehouseTask(celery.Task):
    def __new__(cls, *args, **kwargs):
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

        obj._wh_original_run, obj.run = obj.run, run

        return obj

    def __call__(self, *args, **kwargs):
        return super().__call__(*(self.get_request(),) + args, **kwargs)

    def get_request(self):
        if not hasattr(self.request, "pyramid_env"):
            registry = self.app.pyramid_config.registry
            env = pyramid.scripting.prepare(registry=registry)
            env["request"].tm = transaction.TransactionManager(explicit=True)
            self.request.update(pyramid_env=env)

        return self.request.pyramid_env["request"]

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        if hasattr(self.request, "pyramid_env"):
            pyramid_env = self.request.pyramid_env
            pyramid_env["request"]._process_finished_callbacks()
            pyramid_env["closer"]()

    def apply_async(self, *args, **kwargs):
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

    def _after_commit_hook(self, success, *args, **kwargs):
        if success:
            super().apply_async(*args, **kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("Task id {id} failed.".format(id=task_id), exc_info=einfo)


def task(**kwargs):
    kwargs.setdefault("shared", False)

    def deco(wrapped):
        def callback(scanner, name, wrapped):
            celery_app = scanner.config.registry["celery.app"]
            celery_app.task(**kwargs)(wrapped)

        venusian.attach(wrapped, callback)

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


def includeme(config):
    s = config.registry.settings

    broker_transport_options = {}

    broker_url = s["celery.broker_url"]
    if broker_url.startswith("sqs://"):
        parsed_url = urllib.parse.urlparse(broker_url)
        parsed_query = urllib.parse.parse_qs(parsed_url.query)
        # Celery doesn't handle paths/query arms being passed into the SQS broker,
        # so we'll just remove them from here.
        broker_url = urllib.parse.urlunparse(parsed_url[:2] + ("", "", "", ""))

        if "queue_name_prefix" in parsed_query:
            broker_transport_options["queue_name_prefix"] = (
                parsed_query["queue_name_prefix"][0] + "-"
            )

        if "region" in parsed_query:
            broker_transport_options["region"] = parsed_query["region"][0]

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
        task_queues=(
            Queue("default", routing_key="task.#"),
            Queue("malware", routing_key="malware.#"),
        ),
        task_routes={"warehouse.malware.tasks.*": {"queue": "malware"}},
        task_serializer="json",
        worker_disable_rate_limits=True,
        REDBEAT_REDIS_URL=s["celery.scheduler_url"],
    )
    config.registry["celery.app"].Task = WarehouseTask
    config.registry["celery.app"].pyramid_config = config

    config.action(("celery", "finalize"), config.registry["celery.app"].finalize)

    config.add_directive("add_periodic_task", _add_periodic_task, action_wrap=False)
    config.add_directive("make_celery_app", _get_celery_app, action_wrap=False)
    config.add_directive("task", _get_task_from_config, action_wrap=False)
    config.add_request_method(_get_task_from_request, name="task", reify=True)
