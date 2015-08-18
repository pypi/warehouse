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

from celery import Celery
from pyramid import scripting

from warehouse import celery
from warehouse.config import Environment


def test_configure_celery(monkeypatch):
    configure = pretend.call_recorder(lambda: None)
    monkeypatch.setattr(celery, "configure", configure)

    celery._configure_celery()

    assert configure.calls == [pretend.call()]


class TestWarehouseTask:

    @pytest.mark.parametrize("uses_request", [True, False])
    def test_call(self, monkeypatch, uses_request):
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

        tm_tween_factory = pretend.call_recorder(lambda h, r: h)
        monkeypatch.setattr(celery, "tm_tween_factory", tm_tween_factory)

        if uses_request:
            @pretend.call_recorder
            def runner(irequest):
                assert irequest is request
                return result
        else:
            @pretend.call_recorder
            def runner():
                return result

        task = celery.WarehouseTask()
        task.app = Celery()
        task.app.pyramid_config = pretend.stub(registry=registry)
        task.pyramid = uses_request
        task.run = runner

        assert task() is result
        assert prepare.calls == [pretend.call(registry=registry)]
        assert tm_tween_factory.calls == [pretend.call(mock.ANY, registry)]
        assert prepared["closer"].calls == [pretend.call()]

        if uses_request:
            assert runner.calls == [pretend.call(request)]
        else:
            assert runner.calls == [pretend.call()]


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
