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

from warehouse.ip_addresses.models import BanReason

from ...common.db.ip_addresses import IpAddressFactory


class TestAdminFlag:
    def test_no_ip_not_banned(self, db_request):
        assert not db_request.banned.by_ip("1.2.3.4")

    def test_with_ip_not_banned(self, db_request):
        IpAddressFactory(ip_address="1.2.3.4")
        assert not db_request.banned.by_ip("1.2.3.4")

    def test_with_ip_banned(self, db_request):
        IpAddressFactory(
            ip_address="1.2.3.4",
            is_banned=True,
            ban_reason=BanReason.AUTHENTICATION_ATTEMPTS,
        )
        assert db_request.banned.by_ip("1.2.3.4")
