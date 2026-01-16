# SPDX-License-Identifier: Apache-2.0

from celery.schedules import crontab
from sqlalchemy.orm.base import NO_VALUE

from warehouse import db
from warehouse.accounts.models import Email, User
from warehouse.cache.origin import key_factory, receive_set
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
    compute_2fa_metrics,
    compute_packaging_metrics,
    compute_top_dependents_corpus,
    update_description_html,
)


@db.listens_for(User.name, "set")
def user_name_receive_set(config, target, value, oldvalue, initiator):
    if oldvalue is not NO_VALUE:
        receive_set(User.name, config, target)


@db.listens_for(Email.primary, "set")
def email_primary_receive_set(config, target, value, oldvalue, initiator):
    if oldvalue is not NO_VALUE:
        receive_set(Email.primary, config, target)


@db.listens_for(Organization.name, "set")
def org_name_receive_set(config, target, value, oldvalue, initiator):
    if oldvalue is not NO_VALUE:
        receive_set(Organization.name, config, target)


@db.listens_for(Organization.display_name, "set")
def org_display_name_receive_set(config, target, value, oldvalue, initiator):
    if oldvalue is not NO_VALUE:
        receive_set(Organization.display_name, config, target)


def includeme(config):
    # Register whatever file storage backend has been configured for storing
    # our package files.
    files_storage_class = config.maybe_dotted(config.registry.settings["files.backend"])
    config.register_service_factory(
        files_storage_class.create_service, IFileStorage, name="cache"
    )

    archive_files_storage_class = config.maybe_dotted(
        config.registry.settings["archive_files.backend"]
    )
    config.register_service_factory(
        archive_files_storage_class.create_service, IFileStorage, name="archive"
    )

    simple_storage_class = config.maybe_dotted(
        config.registry.settings["simple.backend"]
    )
    config.register_service_factory(simple_storage_class.create_service, ISimpleStorage)

    docs_storage_class = config.maybe_dotted(config.registry.settings["docs.backend"])
    config.register_service_factory(docs_storage_class.create_service, IDocsStorage)

    project_create_user_limit_string = config.registry.settings.get(
        "warehouse.packaging.project_create_user_ratelimit_string"
    )
    config.register_rate_limiter(
        project_create_user_limit_string, "project.create.user"
    )
    project_create_ip_limit_string = config.registry.settings.get(
        "warehouse.packaging.project_create_ip_ratelimit_string"
    )
    config.register_rate_limiter(project_create_ip_limit_string, "project.create.ip")

    config.register_service_factory(project_service_factory, IProjectService)

    # Register our origin cache keys
    config.register_origin_cache_keys(
        File,
        cache_keys=["project/{obj.release.project.normalized_name}"],
        purge_keys=[key_factory("project/{obj.release.project.normalized_name}")],
    )
    config.register_origin_cache_keys(
        Project,
        cache_keys=["project/{obj.normalized_name}"],
        purge_keys=[
            key_factory("project/{obj.normalized_name}"),
            key_factory("user/{itr.username}", iterate_on="users"),
            key_factory("all-projects"),
            key_factory("org/{attr.normalized_name}", if_attr_exists="organization"),
        ],
    )
    config.register_origin_cache_keys(
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
    )
    config.register_origin_cache_keys(
        Role,
        purge_keys=[
            key_factory("user/{obj.user.username}"),
            key_factory("project/{obj.project.normalized_name}"),
        ],
    )
    config.register_origin_cache_keys(
        User,
        cache_keys=["user/{obj.username}"],
    )
    config.register_origin_cache_keys(
        User.name,
        purge_keys=[
            key_factory("user/{obj.username}"),
            key_factory("org/{itr.normalized_name}", iterate_on="organizations"),
            key_factory("project/{itr.normalized_name}", iterate_on="projects"),
        ],
    )
    config.register_origin_cache_keys(
        Email.primary,
        purge_keys=[
            key_factory("user/{obj.user.username}"),
            key_factory("project/{itr.normalized_name}", iterate_on="user.projects"),
        ],
    )
    config.register_origin_cache_keys(
        Organization,
        cache_keys=["org/{obj.normalized_name}"],
        purge_keys=[
            key_factory("org/{obj.normalized_name}"),
        ],
    )
    config.register_origin_cache_keys(
        Organization.name,
        purge_keys=[
            key_factory("user/{itr.username}", iterate_on="users"),
            key_factory("org/{obj.normalized_name}"),
            key_factory("project/{itr.normalized_name}", iterate_on="projects"),
        ],
    )
    config.register_origin_cache_keys(
        Organization.display_name,
        purge_keys=[
            key_factory("user/{itr.username}", iterate_on="users"),
            key_factory("org/{obj.normalized_name}"),
            key_factory("project/{itr.normalized_name}", iterate_on="projects"),
        ],
    )
    config.register_origin_cache_keys(
        AlternateRepository,
        cache_keys=["project/{obj.project.normalized_name}"],
        purge_keys=[
            key_factory("project/{obj.project.normalized_name}"),
        ],
    )

    config.add_periodic_task(crontab(minute="*/1"), check_file_cache_tasks_outstanding)

    config.add_periodic_task(crontab(minute="*/5"), update_description_html)
    config.add_periodic_task(crontab(minute="*/5"), update_role_invitation_status)

    # Add a periodic task to generate 2FA metrics
    config.add_periodic_task(crontab(minute="*/5"), compute_2fa_metrics)

    # Add a periodic task to generate general metrics
    config.add_periodic_task(crontab(minute="*/5"), compute_packaging_metrics)

    # Add a periodic task to compute dependents corpus once a day
    config.add_periodic_task(crontab(minute=0, hour=5), compute_top_dependents_corpus)
