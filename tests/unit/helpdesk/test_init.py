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

from warehouse.helpdesk import includeme
from warehouse.helpdesk.interfaces import IAdminNotificationService, IHelpDeskService


def test_includeme():
    dummy_klass = pretend.stub(create_service=pretend.stub())
    config = pretend.stub(
        registry=pretend.stub(
            settings={
                "helpdesk.backend": "test.HelpDeskService",
                "helpdesk.notification_backend": "test.NotificationService",
            }
        ),
        maybe_dotted=pretend.call_recorder(lambda n: dummy_klass),
        register_service_factory=pretend.call_recorder(lambda s, i, **kw: None),
    )

    includeme(config)

    assert config.maybe_dotted.calls == [
        pretend.call("test.HelpDeskService"),
        pretend.call("test.NotificationService"),
    ]
    assert config.register_service_factory.calls == [
        pretend.call(dummy_klass.create_service, IHelpDeskService),
        pretend.call(dummy_klass.create_service, IAdminNotificationService),
    ]
