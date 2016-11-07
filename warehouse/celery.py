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

import celery.app.backends

# We need to trick Celery into supporting rediss:// URLs which is how redis-py
# signals that you should use Redis with TLS.
celery.app.backends.BACKEND_ALIASES["rediss"] = "warehouse.celery:TLSRedisBackend"  # noqa

from celery import Celery, Task
from celery.backends.redis import RedisBackend as _RedisBackend
from celery.signals import celeryd_init
from pyramid import scripting
from pyramid.threadlocal import get_current_request
from raven.contrib.celery import register_signal, register_logger_signal

from warehouse.config import Environment, configure


@celeryd_init.connect
def _configure_celery(*args, **kwargs):
    config = configure()
    register_logger_signal(config.registry["raven.client"])
    register_signal(config.registry["raven.client"])


class TLSRedisBackend(_RedisBackend):

    def _params_from_url(self, url, defaults):
        params = super()._params_from_url(url, defaults)
        params.update({"connection_class": self.redis.SSLConnection})
        return params


class WarehouseTask(Task):

    abstract = True

    def __call__(self, *args, **kwargs):
        registry = self.app.pyramid_config.registry
        pyramid_env = scripting.prepare(registry=registry)

        try:
            return super().__call__(pyramid_env["request"], *args, **kwargs)
        finally:
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
            self._after_commit_hook,
            args=args,
            kws=kwargs,
        )

    def _after_commit_hook(self, success, *args, **kwargs):
        if success:
            super().apply_async(*args, **kwargs)


app = Celery("warehouse", strict_typing=False)
app.Task = WarehouseTask


task = app.task


def includeme(config):
    s = config.registry.settings
    app.pyramid_config = config
    app.conf.update(
        accept_content=["json", "msgpack"],
        broker_url=s["celery.broker_url"],
        broker_use_ssl=s["warehouse.env"] == Environment.production,
        result_backend=s["celery.result_url"],
        result_compression="gzip",
        result_serializer="json",
        task_queue_ha_policy="all",
        task_serializer="json",
        worker_disable_rate_limits=True,
    )
