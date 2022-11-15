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

from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.services import subscription_factory


def includeme(config):
    # Register our subscription service
    config.register_service_factory(subscription_factory, ISubscriptionService)
    # Register whatever payment service provider has been configured
    billing_class = config.maybe_dotted(config.registry.settings["billing.backend"])
    config.register_service_factory(billing_class.create_service, IBillingService)
