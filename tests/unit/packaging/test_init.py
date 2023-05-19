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
from warehouse.organizations.models import Organization
from warehouse.packaging.interfaces import (
    IDocsStorage,
    IFileStorage,
    IProjectService,
    ISimpleStorage,
)
from warehouse.packaging.models import File, Project, Release, Role
from warehouse.packaging.services import project_service_factory
from warehouse.packaging.tasks import (  # sync_bigquery_release_files,
    check_file_cache_tasks_outstanding,
    compute_2fa_mandate,
    update_description_html,
)
from warehouse.rate_limiting import IRateLimiter, RateLimit


@pytest.mark.parametrize("with_bq_sync", [True, False])
@pytest.mark.parametrize("with_2fa_mandate", [True, False])
def test_includeme(monkeypatch, with_bq_sync, with_2fa_mandate):
    storage_class = pretend.stub(
        create_service=pretend.call_recorder(lambda *a, **kw: pretend.stub())
    )

    def key_factory(keystring, iterate_on=None, if_attr_exists=None):
        return pretend.call(
            keystring, iterate_on=iterate_on, if_attr_exists=if_attr_exists
        )

    monkeypatch.setattr(packaging, "key_factory", key_factory)
    settings = {
        "files.backend": "foo.bar",
        "archive_files.backend": "peas.carrots",
        "simple.backend": "bread.butter",
        "docs.backend": "wu.tang",
        "warehouse.packaging.project_create_user_ratelimit_string": "20 per hour",
        "warehouse.packaging.project_create_ip_ratelimit_string": "40 per hour",
    }
    if with_bq_sync:
        settings["warehouse.release_files_table"] = "fizzbuzz"
    if with_2fa_mandate:
        settings["warehouse.two_factor_mandate.available"] = True

    config = pretend.stub(
        maybe_dotted=lambda dotted: storage_class,
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
        registry=pretend.stub(settings=settings),
        register_origin_cache_keys=pretend.call_recorder(lambda c, **kw: None),
        get_settings=lambda: settings,
        add_periodic_task=pretend.call_recorder(lambda *a, **kw: None),
    )

    packaging.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(storage_class.create_service, IFileStorage, name="cache"),
        pretend.call(storage_class.create_service, IFileStorage, name="archive"),
        pretend.call(storage_class.create_service, ISimpleStorage),
        pretend.call(storage_class.create_service, IDocsStorage),
        pretend.call(
            RateLimit("20 per hour"), IRateLimiter, name="project.create.user"
        ),
        pretend.call(RateLimit("40 per hour"), IRateLimiter, name="project.create.ip"),
        pretend.call(project_service_factory, IProjectService),
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
                key_factory(
                    "org/{attr.normalized_name}", if_attr_exists="organization"
                ),
            ],
        ),
        pretend.call(
            Release,
            cache_keys=["project/{obj.project.normalized_name}"],
            purge_keys=[
                key_factory("project/{obj.project.normalized_name}"),
                key_factory("user/{itr.username}", iterate_on="project.users"),
                key_factory("all-projects"),
                key_factory(
                    "org/{attr.normalized_name}", if_attr_exists="project.organization"
                ),
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
                key_factory("org/{itr.normalized_name}", iterate_on="organizations"),
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
        pretend.call(
            Organization,
            cache_keys=["org/{obj.normalized_name}"],
            purge_keys=[
                key_factory("org/{obj.normalized_name}"),
            ],
        ),
        pretend.call(
            Organization.name,
            purge_keys=[
                key_factory("user/{itr.username}", iterate_on="users"),
                key_factory("org/{obj.normalized_name}"),
                key_factory("project/{itr.normalized_name}", iterate_on="projects"),
            ],
        ),
        pretend.call(
            Organization.display_name,
            purge_keys=[
                key_factory("user/{itr.username}", iterate_on="users"),
                key_factory("org/{obj.normalized_name}"),
                key_factory("project/{itr.normalized_name}", iterate_on="projects"),
            ],
        ),
    ]

    if with_bq_sync:
        # assert (
        #    pretend.call(crontab(minute=0), sync_bigquery_release_files)
        #    in config.add_periodic_task.calls
        # )
        pass

    if with_2fa_mandate:
        assert (
            pretend.call(crontab(minute=0, hour=3), compute_2fa_mandate)
            in config.add_periodic_task.calls
        )

    assert (
        pretend.call(crontab(minute="*/1"), check_file_cache_tasks_outstanding)
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
