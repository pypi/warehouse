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

from celery.schedules import crontab

from warehouse import organizations
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.services import database_organization_factory
from warehouse.organizations.tasks import (
    delete_declined_organization_applications,
    update_organization_invitation_status,
    update_organziation_subscription_usage_record,
)


def test_includeme():
    config = pretend.stub(
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
        add_periodic_task=pretend.call_recorder(lambda *a, **kw: None),
    )

    organizations.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(database_organization_factory, IOrganizationService),
    ]

    assert config.add_periodic_task.calls == [
        pretend.call(crontab(minute="*/5"), update_organization_invitation_status),
        pretend.call(
            crontab(minute=0, hour=0), delete_declined_organization_applications
        ),
        pretend.call(
            crontab(minute=0, hour=0), update_organziation_subscription_usage_record
        ),
    ]
