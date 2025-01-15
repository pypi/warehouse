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

from __future__ import annotations

import typing

from .interfaces import IAdminNotificationService, IHelpDeskService

if typing.TYPE_CHECKING:
    from pyramid.config import Configurator


def includeme(config: Configurator) -> None:
    helpdesk_class = config.maybe_dotted(config.registry.settings["helpdesk.backend"])
    notification_class = config.maybe_dotted(
        config.registry.settings["helpdesk.notification_backend"]
    )

    config.register_service_factory(helpdesk_class.create_service, IHelpDeskService)
    config.register_service_factory(
        notification_class.create_service, IAdminNotificationService
    )
