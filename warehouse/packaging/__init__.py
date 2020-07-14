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
from warehouse.packaging.interfaces import IDocsStorage, IFileStorage
from warehouse.packaging.models import File, Project, Release, Role
from warehouse.packaging.tasks import (
    compute_trending,
    sync_bigquery_release_files,
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


def includeme(config):
    # Register whatever file storage backend has been configured for storing
    # our package files.
    files_storage_class = config.maybe_dotted(config.registry.settings["files.backend"])
    config.register_service_factory(files_storage_class.create_service, IFileStorage)

    docs_storage_class = config.maybe_dotted(config.registry.settings["docs.backend"])
    config.register_service_factory(docs_storage_class.create_service, IDocsStorage)

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
        ],
    )
    config.register_origin_cache_keys(
        Release,
        cache_keys=["project/{obj.project.normalized_name}"],
        purge_keys=[
            key_factory("project/{obj.project.normalized_name}"),
            key_factory("user/{itr.username}", iterate_on="project.users"),
            key_factory("all-projects"),
        ],
    )
    config.register_origin_cache_keys(
        Role,
        purge_keys=[
            key_factory("user/{obj.user.username}"),
            key_factory("project/{obj.project.normalized_name}"),
        ],
    )
    config.register_origin_cache_keys(User, cache_keys=["user/{obj.username}"])
    config.register_origin_cache_keys(
        User.name,
        purge_keys=[
            key_factory("user/{obj.username}"),
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

    config.add_periodic_task(crontab(minute="*/5"), update_description_html)

    # Add a periodic task to compute trending once a day, assuming we have
    # been configured to be able to access BigQuery.
    if config.get_settings().get("warehouse.trending_table"):
        config.add_periodic_task(crontab(minute=0, hour=3), compute_trending)

    if config.get_settings().get("warehouse.release_files_table"):
        config.add_periodic_task(crontab(minute="*/15"), sync_bigquery_release_files)
