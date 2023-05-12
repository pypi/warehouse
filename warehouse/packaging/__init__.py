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
from warehouse.packaging.models import File, Project, Release, Role
from warehouse.packaging.services import project_service_factory
from warehouse.packaging.tasks import (
    check_file_cache_tasks_outstanding,
    compute_2fa_mandate,
    compute_2fa_metrics,
    update_description_html,
)
from warehouse.rate_limiting import IRateLimiter, RateLimit


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
    config.register_service_factory(
        RateLimit(project_create_user_limit_string),
        IRateLimiter,
        name="project.create.user",
    )
    project_create_ip_limit_string = config.registry.settings.get(
        "warehouse.packaging.project_create_ip_ratelimit_string"
    )
    config.register_service_factory(
        RateLimit(project_create_ip_limit_string),
        IRateLimiter,
        name="project.create.ip",
    )

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

    config.add_periodic_task(crontab(minute="*/1"), check_file_cache_tasks_outstanding)

    config.add_periodic_task(crontab(minute="*/5"), update_description_html)
    config.add_periodic_task(crontab(minute="*/5"), update_role_invitation_status)

    # Add a periodic task to recompute the critical projects list once a day
    if config.get_settings().get("warehouse.two_factor_mandate.available", False):
        config.add_periodic_task(crontab(minute=0, hour=3), compute_2fa_mandate)

    # Add a periodic task to generate 2FA metrics
    config.add_periodic_task(crontab(minute="*/5"), compute_2fa_metrics)

    # TODO: restore this
    # if config.get_settings().get("warehouse.release_files_table"):
    #     config.add_periodic_task(crontab(minute=0), sync_bigquery_release_files)
