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

from ...common.db.subscriptions import SubscriptionFactory as DBSubscriptionFactory


class TestSubscription:
    def test_is_restricted(self, db_session):
        subscription = DBSubscriptionFactory.create(status="past_due")
        assert subscription.is_restricted

    def test_not_is_restricted(self, db_session):
        subscription = DBSubscriptionFactory.create()
        assert not subscription.is_restricted
