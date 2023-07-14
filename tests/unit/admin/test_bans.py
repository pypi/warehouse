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

from sqlalchemy import sql

from warehouse.ip_addresses.models import BanReason

from ...common.db.ip_addresses import IpAddressFactory


class TestAdminFlag:
    def test_no_ip_not_banned(self, db_request):
        assert not db_request.banned.by_ip("4.3.2.1")

    def test_with_ip_not_banned(self, db_request):
        assert not db_request.banned.by_ip(db_request.ip_address.ip_address)

    def test_with_ip_banned(self, db_request):
        user_service = pretend.stub(
            _hit_ratelimits=pretend.call_recorder(lambda userid=None: None),
            _check_ratelimits=pretend.call_recorder(
                lambda userid=None, tags=None: None
            ),
        )
        db_request.find_service = lambda service_name, context=None: user_service
        ip_addy = IpAddressFactory(
            is_banned=True,
            ban_reason=BanReason.AUTHENTICATION_ATTEMPTS,
            ban_date=sql.func.now(),
        )
        assert db_request.banned.by_ip(ip_addy.ip_address)
        assert user_service._hit_ratelimits.calls == [pretend.call(userid=None)]
        assert user_service._check_ratelimits.calls == [
            pretend.call(userid=None, tags=["banned:by_ip"])
        ]
