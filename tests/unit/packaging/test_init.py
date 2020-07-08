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
from warehouse.accounts.models import Email, User
from warehouse.packaging.interfaces import IDocsStorage, IFileStorage
from warehouse.packaging.models import File, Project, Release, Role
from warehouse.packaging.tasks import (
    compute_trending,
    sync_bigquery_release_files,
    update_description_html,
)


@pytest.mark.parametrize(
    ("with_trending", "with_bq_sync"),
    ([True, True], [True, False], [False, True], [False, False]),
)
def test_includeme(monkeypatch, with_trending, with_bq_sync):
    storage_class = pretend.stub(
        create_service=pretend.call_recorder(lambda *a, **kw: pretend.stub())
    )

    def key_factory(keystring, iterate_on=None):
        return pretend.call(keystring, iterate_on=iterate_on)

    monkeypatch.setattr(packaging, "key_factory", key_factory)
    settings = dict()
    if with_trending:
        settings["warehouse.trending_table"] = "foobar"
    if with_bq_sync:
        settings["warehouse.release_files_table"] = "fizzbuzz"

    config = pretend.stub(
        maybe_dotted=lambda dotted: storage_class,
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
        registry=pretend.stub(
            settings={"files.backend": "foo.bar", "docs.backend": "wu.tang"}
        ),
        register_origin_cache_keys=pretend.call_recorder(lambda c, **kw: None),
        get_settings=lambda: settings,
        add_periodic_task=pretend.call_recorder(lambda *a, **kw: None),
    )

    packaging.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(storage_class.create_service, IFileStorage),
        pretend.call(storage_class.create_service, IDocsStorage),
    ]
    assert config.register_origin_cache_keys.calls == [
        pretend.call(
            File,
            cache_keys=["project/{obj.release.project.normalized_name}"],
            purge_keys=[key_factory("project/{obj.release.project.normalized_name}")],
        ),
        pretend.call(
            Project,
            cache_keys=["project/{obj.normalized_name}"],
            purge_keys=[
                key_factory("project/{obj.normalized_name}"),
                key_factory("user/{itr.username}", iterate_on="users"),
                key_factory("all-projects"),
            ],
        ),
        pretend.call(
            Release,
            cache_keys=["project/{obj.project.normalized_name}"],
            purge_keys=[
                key_factory("project/{obj.project.normalized_name}"),
                key_factory("user/{itr.username}", iterate_on="project.users"),
                key_factory("all-projects"),
            ],
        ),
        pretend.call(
            Role,
            purge_keys=[
                key_factory("user/{obj.user.username}"),
                key_factory("project/{obj.project.normalized_name}"),
            ],
        ),
        pretend.call(User, cache_keys=["user/{obj.username}"]),
        pretend.call(
            User.name,
            purge_keys=[
                key_factory("user/{obj.username}"),
                key_factory("project/{itr.normalized_name}", iterate_on="projects"),
            ],
        ),
        pretend.call(
            Email.primary,
            purge_keys=[
                key_factory("user/{obj.user.username}"),
                key_factory(
                    "project/{itr.normalized_name}", iterate_on="user.projects"
                ),
            ],
        ),
    ]

    if with_trending and with_bq_sync:
        assert config.add_periodic_task.calls == [
            pretend.call(crontab(minute="*/5"), update_description_html),
            pretend.call(crontab(minute=0, hour=3), compute_trending),
            pretend.call(crontab(minute="*/60"), sync_bigquery_release_files),
        ]
    elif with_bq_sync:
        assert config.add_periodic_task.calls == [
            pretend.call(crontab(minute="*/5"), update_description_html),
            pretend.call(crontab(minute="*/60"), sync_bigquery_release_files),
        ]
    elif with_trending:
        assert config.add_periodic_task.calls == [
            pretend.call(crontab(minute="*/5"), update_description_html),
            pretend.call(crontab(minute=0, hour=3), compute_trending),
        ]
    else:
        assert config.add_periodic_task.calls == [
            pretend.call(crontab(minute="*/5"), update_description_html)
        ]
