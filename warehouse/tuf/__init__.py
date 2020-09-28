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

from warehouse.tuf.constants import (
    BIN_N_COUNT,
    BIN_N_ROLE,
    BINS_ROLE,
    HASH_ALGORITHM,
    TOPLEVEL_ROLES,
)
from warehouse.tuf.interfaces import IKeyService, IRepositoryService, IStorageService
from warehouse.tuf.tasks import bump_role


def includeme(config):
    config.add_settings(
        {
            "tuf.keytype": "ed25519",
            "tuf.root.threshold": 1,
            "tuf.root.expiry": 31536000,
            "tuf.snapshot.threshold": 1,
            "tuf.snapshot.expiry": 86400,
            "tuf.targets.threshold": 1,
            "tuf.targets.expiry": 31536000,
            "tuf.timestamp.threshold": 1,
            "tuf.timestamp.expiry": 86400,
            "tuf.bins.threshold": 1,
            "tuf.bins.expiry": 31536000,
            "tuf.bin-n.threshold": 1,
            # NOTE: This is a deviation from PEP 458, as published: the PEP
            # stipulates that bin-n metadata expires every 24 hours, which is
            # both burdensome for mirrors and requires a large number of redundant
            # signing operations even when the targets themselves do not change.
            # An amended version of the PEP should be published, at which point
            # this note can be removed.
            "tuf.bin-n.expiry": 604800,
            "tuf.spec_version": "1.0.0",
        }
    )

    key_service_class = config.maybe_dotted(config.registry.settings["tuf.key_backend"])
    config.register_service_factory(key_service_class.create_service, IKeyService)

    storage_service_class = config.maybe_dotted(
        config.registry.settings["tuf.storage_backend"]
    )
    config.register_service_factory(
        storage_service_class.create_service, IStorageService
    )

    repo_service_class = config.maybe_dotted(
        config.registry.settings["tuf.repo_backend"]
    )
    config.register_service_factory(
        repo_service_class.create_service, IRepositoryService
    )

    # Per PEP458: The timestamp, snapshot, and bins metadata expire every 24 hours.
    # We conservatively bump every 6 hours.
    config.add_periodic_task(
        crontab(minute=0, hour="*/6"), bump_role, args=("timestamp",)
    )
    config.add_periodic_task(
        crontab(minute=0, hour="*/6"), bump_role, args=("snapshot",)
    )
    config.add_periodic_task(crontab(minute=0, hour="*/6"), bump_role, args=("bins",))
