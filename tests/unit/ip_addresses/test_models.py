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

import pytest

from sqlalchemy import sql
from sqlalchemy.exc import IntegrityError

from warehouse.ip_addresses.models import BanReason

from ...common.db.ip_addresses import IpAddressFactory as DBIpAddressFactory


class TestIpAddress:
    def test_repr(self, db_request):
        ip_address = db_request.ip_address
        assert isinstance(repr(ip_address), str)
        assert repr(ip_address) == "1.2.3.4"

    def test_invalid_transformed(self, db_request):
        ip_address = DBIpAddressFactory(ip_address="wutang")
        assert repr(ip_address) == "192.0.2.69"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"ip_address": "1.2.3.4", "is_banned": True},
            {
                "ip_address": "1.2.3.4",
                "is_banned": True,
                "ban_reason": BanReason.AUTHENTICATION_ATTEMPTS,
            },
            {"ip_address": "1.2.3.4", "is_banned": True, "ban_date": sql.func.now()},
            {
                "ip_address": "1.2.3.4",
                "is_banned": False,
                "ban_reason": BanReason.AUTHENTICATION_ATTEMPTS,
            },
            {"ip_address": "1.2.3.4", "is_banned": False, "ban_date": sql.func.now()},
            {
                "ip_address": "1.2.3.4",
                "is_banned": False,
                "ban_reason": BanReason.AUTHENTICATION_ATTEMPTS,
                "ban_date": sql.func.now(),
            },
        ],
    )
    def test_ban_data_constraint(self, db_request, kwargs):
        with pytest.raises(IntegrityError):
            DBIpAddressFactory(**kwargs)
