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

from warehouse import packaging
from warehouse.packaging.interfaces import IDownloadStatService
from warehouse.packaging.models import Project, Release


def test_includme(monkeypatch):
    download_stat_service_obj = pretend.stub()
    download_stat_service_cls = pretend.call_recorder(
        lambda url: download_stat_service_obj
    )
    monkeypatch.setattr(
        packaging, "RedisDownloadStatService", download_stat_service_cls,
    )

    config = pretend.stub(
        register_service=pretend.call_recorder(
            lambda iface, svc: download_stat_service_cls
        ),
        registry=pretend.stub(settings={"download_stats.url": pretend.stub()}),
        register_origin_cache_keys=pretend.call_recorder(lambda c, *k: None),
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
    assert config.register_origin_cache_keys.calls == [
        pretend.call(
            Project,
            "project",
            "project/{obj.normalized_name}",
        ),
        pretend.call(
            Release,
            "project",
            "project/{obj.project.normalized_name}",
        ),
    ]
