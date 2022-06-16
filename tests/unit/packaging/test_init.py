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
from warehouse.manage.tasks import update_role_invitation_status
from warehouse.packaging.interfaces import IDocsStorage, IFileStorage, ISimpleStorage
from warehouse.packaging.models import File, Project, Release, Role
from warehouse.packaging.tasks import (  # sync_bigquery_release_files,
    compute_2fa_mandate,
    compute_trending,
    update_description_html,
)


@pytest.mark.parametrize("with_trending", [True, False])
@pytest.mark.parametrize("with_bq_sync", [True, False])
@pytest.mark.parametrize("with_2fa_mandate", [True, False])
def test_includeme(monkeypatch, with_trending, with_bq_sync, with_2fa_mandate):
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
    if with_2fa_mandate:
        settings["warehouse.two_factor_mandate.available"] = True

    config = pretend.stub(
        maybe_dotted=lambda dotted: storage_class,
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
        registry=pretend.stub(
            settings={
                "files.backend": "foo.bar",
                "simple.backend": "bread.butter",
                "docs.backend": "wu.tang",
            }
        ),
        register_origin_cache_keys=pretend.call_recorder(lambda c, **kw: None),
        get_settings=lambda: settings,
        add_periodic_task=pretend.call_recorder(lambda *a, **kw: None),
    )

    packaging.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(storage_class.create_service, IFileStorage),
        pretend.call(storage_class.create_service, ISimpleStorage),
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

    if with_bq_sync:
        # assert (
        #    pretend.call(crontab(minute=0), sync_bigquery_release_files)
        #    in config.add_periodic_task.calls
        # )
        pass

    if with_trending:
        assert (
            pretend.call(crontab(minute=0, hour=3), compute_trending)
            in config.add_periodic_task.calls
        )

    if with_2fa_mandate:
        assert (
            pretend.call(crontab(minute=0, hour=3), compute_2fa_mandate)
            in config.add_periodic_task.calls
        )

    assert (
        pretend.call(crontab(minute="*/5"), update_description_html)
        in config.add_periodic_task.calls
    )
    assert (
        pretend.call(crontab(minute="*/5"), update_role_invitation_status)
        in config.add_periodic_task.calls
    )
