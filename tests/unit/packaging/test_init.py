# SPDX-License-Identifier: Apache-2.0

import pretend

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
from warehouse.packaging.models import AlternateRepository, File, Project, Release, Role
from warehouse.packaging.services import project_service_factory
from warehouse.packaging.tasks import (
    check_file_cache_tasks_outstanding,
    update_description_html,
)
from warehouse.rate_limiting import IRateLimiter, RateLimit


def test_includeme(monkeypatch):
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
            RateLimit("20 per hour", identifiers=["project.create.user"]),
            IRateLimiter,
            name="project.create.user",
        ),
        pretend.call(
            RateLimit("40 per hour", identifiers=["project.create.ip"]),
            IRateLimiter,
            name="project.create.ip",
        ),
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
        pretend.call(
            AlternateRepository,
            cache_keys=["project/{obj.project.normalized_name}"],
            purge_keys=[
                key_factory("project/{obj.project.normalized_name}"),
            ],
        ),
    ]

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
