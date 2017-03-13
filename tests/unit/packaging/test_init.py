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

from celery.schedules import crontab

from warehouse import packaging
from warehouse.packaging.interfaces import IDownloadStatService, IFileStorage
from warehouse.packaging.models import Project, Release
from warehouse.packaging.tasks import compute_trending


@pytest.mark.parametrize("with_trending", [True, False])
def test_includme(monkeypatch, with_trending):
    storage_class = pretend.stub(create_service=pretend.stub())

    download_stat_service_obj = pretend.stub()
    download_stat_service_cls = pretend.call_recorder(
        lambda url: download_stat_service_obj
    )
    monkeypatch.setattr(
        packaging, "RedisDownloadStatService", download_stat_service_cls,
    )

    config = pretend.stub(
        maybe_dotted=lambda dotted: storage_class,
        register_service=pretend.call_recorder(
            lambda iface, svc: download_stat_service_cls
        ),
        register_service_factory=pretend.call_recorder(
            lambda factory, iface: None,
        ),
        registry=pretend.stub(
            settings={
                "download_stats.url": pretend.stub(),
                "files.backend": "foo.bar",
            },
        ),
        register_origin_cache_keys=pretend.call_recorder(lambda c, **kw: None),
        get_settings=lambda: (
            {"warehouse.trending_table": "foobar"} if with_trending else {}),
        add_periodic_task=pretend.call_recorder(lambda *a, **kw: None),
    )

    packaging.includeme(config)

    assert download_stat_service_cls.calls == [
        pretend.call(config.registry.settings["download_stats.url"]),
    ]

    assert config.register_service.calls == [
        pretend.call(
            download_stat_service_obj,
            IDownloadStatService,
        ),
    ]
    assert config.register_service_factory.calls == [
        pretend.call(storage_class.create_service, IFileStorage),
    ]
    assert config.register_origin_cache_keys.calls == [
        pretend.call(
            Project,
            cache_keys=["project/{obj.normalized_name}"],
            purge_keys=["project/{obj.normalized_name}", "all-projects"],
        ),
        pretend.call(
            Release,
            cache_keys=["project/{obj.project.normalized_name}"],
            purge_keys=[
                "project/{obj.project.normalized_name}",
                "all-projects",
            ],
        ),
    ]

    if with_trending:
        assert config.add_periodic_task.calls == [
            pretend.call(crontab(minute=0, hour=3), compute_trending),
        ]
