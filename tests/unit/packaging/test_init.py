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
from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.models import Project, Release, Role
from warehouse.packaging.tasks import compute_trending


@pytest.mark.parametrize("with_trending", [True, False])
def test_includme(monkeypatch, with_trending):
    storage_class = pretend.stub(create_service=pretend.stub())

    def key_factory(keystring, iterate_on=None):
        return pretend.call(keystring, iterate_on=iterate_on)

    monkeypatch.setattr(packaging, 'key_factory', key_factory)

    config = pretend.stub(
        maybe_dotted=lambda dotted: storage_class,
        register_service_factory=pretend.call_recorder(
            lambda factory, iface: None,
        ),
        registry=pretend.stub(
            settings={
                "files.backend": "foo.bar",
            },
        ),
        register_origin_cache_keys=pretend.call_recorder(lambda c, **kw: None),
        get_settings=lambda: (
            {"warehouse.trending_table": "foobar"} if with_trending else {}),
        add_periodic_task=pretend.call_recorder(lambda *a, **kw: None),
    )

    packaging.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(storage_class.create_service, IFileStorage),
    ]
    assert config.register_origin_cache_keys.calls == [
        pretend.call(
            Project,
            cache_keys=["project/{obj.normalized_name}"],
            purge_keys=[
                key_factory("project/{obj.normalized_name}"),
                key_factory("user/{itr.username}", iterate_on='users'),
                key_factory("all-projects"),
            ],
        ),
        pretend.call(
            Release,
            cache_keys=["project/{obj.project.normalized_name}"],
            purge_keys=[
                key_factory("project/{obj.project.normalized_name}"),
                key_factory("user/{itr.username}", iterate_on='project.users'),
                key_factory("all-projects"),
            ],
        ),
        pretend.call(
            Role,
            purge_keys=[
                key_factory("user/{obj.user.username}"),
                key_factory("project/{obj.project.normalized_name}")
            ],
        ),
        pretend.call(
            User,
            cache_keys=["user/{obj.username}"],
        ),
        pretend.call(
            User.name,
            purge_keys=[
                key_factory("user/{obj.username}"),
                key_factory(
                    "project/{itr.normalized_name}",
                    iterate_on='projects',
                ),
            ],
        ),
        pretend.call(
            Email.primary,
            purge_keys=[
                key_factory("user/{obj.user.username}"),
                key_factory(
                    "project/{itr.normalized_name}",
                    iterate_on='user.projects',
                ),
            ],
        ),
    ]

    if with_trending:
        assert config.add_periodic_task.calls == [
            pretend.call(crontab(minute=0, hour=3), compute_trending),
        ]
