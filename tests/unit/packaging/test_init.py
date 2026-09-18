# SPDX-License-Identifier: Apache-2.0

import types

from celery.schedules import crontab

from warehouse import packaging
from warehouse.accounts.models import Email, User
from warehouse.manage.tasks import update_role_invitation_status
from warehouse.organizations.models import Organization, OrganizationProject
from warehouse.packaging.interfaces import (
    IDocsStorage,
    IFileStorage,
    IProjectService,
    ISimpleStorage,
)
from warehouse.packaging.models import File, Project, Release, Role
from warehouse.packaging.services import LocalFileStorage, project_service_factory
from warehouse.packaging.tasks import (
    check_file_cache_tasks_outstanding,
    reconcile_file_storages,
    update_description_html,
)


def test_includeme(mocker):
    def key_factory(keystring, iterate_on=None, if_attr_exists=None):
        """Stand in for the real factory, whose closure isn't comparable."""
        return types.SimpleNamespace(
            keystring=keystring,
            iterate_on=iterate_on,
            if_attr_exists=if_attr_exists,
        )

    mocker.patch.object(
        packaging, "key_factory", autospec=True, side_effect=key_factory
    )
    settings = {
        "files.backend": "foo.bar",
        "archive_files.backend": "peas.carrots",
        "simple.backend": "bread.butter",
        "docs.backend": "wu.tang",
        "warehouse.packaging.project_create_user_ratelimit_string": "20 per hour",
        "warehouse.packaging.project_create_ip_ratelimit_string": "40 per hour",
        "warehouse.packaging.project_create_organization_ratelimit_string": (
            "10 per day"
        ),
    }

    config = mocker.Mock(
        spec=[
            "maybe_dotted",
            "register_service_factory",
            "register_rate_limiter",
            "register_origin_cache_keys",
            "registry",
            "add_periodic_task",
        ]
    )
    config.maybe_dotted.return_value = LocalFileStorage
    config.registry = types.SimpleNamespace(settings=settings)

    packaging.includeme(config)

    assert config.register_service_factory.call_args_list == [
        mocker.call(LocalFileStorage.create_service, IFileStorage, name="cache"),
        mocker.call(LocalFileStorage.create_service, IFileStorage, name="archive"),
        mocker.call(LocalFileStorage.create_service, ISimpleStorage),
        mocker.call(LocalFileStorage.create_service, IDocsStorage),
        mocker.call(project_service_factory, IProjectService),
    ]
    assert config.register_rate_limiter.call_args_list == [
        mocker.call("20 per hour", "project.create.user"),
        mocker.call("40 per hour", "project.create.ip"),
        mocker.call("10 per day", "project.create.organization"),
    ]
    assert config.register_origin_cache_keys.call_args_list == [
        mocker.call(
            File,
            cache_keys=["project/{obj.release.project.normalized_name}"],
            purge_keys=[key_factory("project/{obj.release.project.normalized_name}")],
        ),
        mocker.call(
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
        mocker.call(
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
        mocker.call(
            Role,
            purge_keys=[
                key_factory("user/{obj.user.username}"),
                key_factory("project/{obj.project.normalized_name}"),
            ],
        ),
        mocker.call(User, cache_keys=["user/{obj.username}"]),
        mocker.call(
            User.name,
            purge_keys=[
                key_factory("user/{obj.username}"),
                key_factory("org/{itr.normalized_name}", iterate_on="organizations"),
                key_factory("project/{itr.normalized_name}", iterate_on="projects"),
            ],
        ),
        mocker.call(
            Email.primary,
            purge_keys=[
                key_factory("user/{obj.user.username}"),
                key_factory(
                    "project/{itr.normalized_name}", iterate_on="user.projects"
                ),
            ],
        ),
        mocker.call(
            Organization,
            cache_keys=["org/{obj.normalized_name}"],
            purge_keys=[
                key_factory("org/{obj.normalized_name}"),
            ],
        ),
        mocker.call(
            Organization.name,
            purge_keys=[
                key_factory("user/{itr.username}", iterate_on="users"),
                key_factory("org/{obj.normalized_name}"),
                key_factory("project/{itr.normalized_name}", iterate_on="projects"),
            ],
        ),
        mocker.call(
            Organization.display_name,
            purge_keys=[
                key_factory("user/{itr.username}", iterate_on="users"),
                key_factory("org/{obj.normalized_name}"),
                key_factory("project/{itr.normalized_name}", iterate_on="projects"),
            ],
        ),
        mocker.call(
            OrganizationProject,
            purge_keys=[
                key_factory("project/{attr.normalized_name}", if_attr_exists="project"),
            ],
        ),
    ]

    assert (
        mocker.call(crontab(minute="*/1"), check_file_cache_tasks_outstanding)
        in config.add_periodic_task.call_args_list
    )
    assert (
        mocker.call(crontab(minute="*/15"), reconcile_file_storages)
        in config.add_periodic_task.call_args_list
    )
    assert (
        mocker.call(crontab(minute="*/5"), update_description_html)
        in config.add_periodic_task.call_args_list
    )
    assert (
        mocker.call(crontab(minute="*/5"), update_role_invitation_status)
        in config.add_periodic_task.call_args_list
    )
