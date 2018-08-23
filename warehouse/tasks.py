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

import dramatiq
import pyramid.scripting
import venusian
import transaction

from dramatiq.middleware import (
    AgeLimit,
    TimeLimit,
    ShutdownNotifications,
    Callbacks,
    Pipelines,
    Retries,
)
from dramatiq_sqs import SQSBroker


def with_request(fn, *, registry):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        env = pyramid.scripting.prepare(registry=registry)
        request = env["request"]
        request.tm = transaction.TransactionManager(explicit=True)

        try:
            with request.tm:
                return fn(request, *args, **kwargs)
        finally:
            request._process_finished_callbacks()
            env["closer"]()

    return wrapped


class TransactionAwareActor(dramatiq.Actor):
    def send(self, request, *args, **kwargs):
        return self.send_with_options(request, args=args, kwargs=kwargs)

    def send_with_options(self, request, **kwargs):
        if not hasattr(request, "tm"):
            return super().send_with_options(**kwargs)
        else:
            request.tm.get().addAfterCommitHook(self._after_commit_hook, kws=kwargs)

    def _after_commit_hook(self, success, **kwargs):
        if success:
            super().send_with_options(**kwargs)

        def _after_commit_hook(self, success, *args, **kwargs):
            if success:
                super().apply_async(*args, **kwargs)


class RequestAwareActorProxy:
    def __init__(self, request, actor):
        self._request = request
        self._actor = actor

    def send(self, *args, **kwargs):
        return self._actor.send(self._request, *args, **kwargs)

    def send_with_options(self, *args, **kwargs):
        return self._actor.send(self._request, *args, **kwargs)


def task(fn=None, *, actor_name=None, queue_name="default", priority=0, **options):
    def deco(wrapped, *, depth=1):
        wrapped.__actor_name__ = actor_name or wrapped.__name__

        def callback(context, name, wrapped):
            config = context.config.with_package(info.module)
            broker = config.registry["dramatiq.broker"]
            actor_name = wrapped.__actor_name__

            invalid_options = set(options) - broker.actor_options
            if invalid_options:
                invalid_options_list = ", ".join(invalid_options)
                raise ValueError(
                    (
                        "The following actor options are undefined: %s. "
                        "Did you forget to add a middleware to your Broker?"
                    )
                    % invalid_options_list
                )

            TransactionAwareActor(
                with_request(wrapped, registry=config.registry),
                actor_name=actor_name,
                queue_name=queue_name,
                priority=priority,
                broker=broker,
                options=options,
            )

        info = venusian.attach(wrapped, callback, depth=depth)

        return wrapped

    if fn is None:
        return deco
    return deco(fn, depth=2)


def _get_task_from_request(request, task):
    if not hasattr(task, "__actor_name__"):
        raise ValueError(f"Invalid task: {task!r}")

    return RequestAwareActorProxy(
        request, request.registry["dramatiq.broker"].actors[task.__actor_name__]
    )


def _make_broker(config):
    return config.registry["dramatiq.broker"]


def includeme(config):
    # # sqs://localstack:4576/warehouse-dev?region=us-east-1
    # TODO: Handle Real URLs for SQS
    # TODO: Datadog Metrics
    config.registry["dramatiq.broker"] = SQSBroker(
        middleware=[
            AgeLimit(),
            TimeLimit(),
            ShutdownNotifications(),
            Callbacks(),
            Pipelines(),
            Retries(),
        ],
        endpoint_url="http://localstack:4576",
        region_name="us-east-1",
        use_ssl=False,
    )
    config.add_directive("make_broker", _make_broker, action_wrap=False)
    config.add_request_method(_get_task_from_request, name="task")
    # TODO: Actually Handle Periodic Tasks
    config.add_directive("add_periodic_task", lambda *a, **kw: None, action_wrap=False)
