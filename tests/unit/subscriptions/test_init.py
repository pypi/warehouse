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

from warehouse import subscriptions
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.services import subscription_factory


def test_includeme():
    billing_class = pretend.stub(
        create_service=pretend.call_recorder(lambda *a, **kw: pretend.stub())
    )

    settings = dict()

    config = pretend.stub(
        maybe_dotted=lambda dotted: billing_class,
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
        registry=pretend.stub(
            settings={
                "billing.backend": "hand.some",
            }
        ),
        get_settings=lambda: settings,
    )

    subscriptions.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(subscription_factory, ISubscriptionService),
        pretend.call(billing_class.create_service, IBillingService),
    ]
