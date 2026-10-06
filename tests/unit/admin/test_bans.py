# SPDX-License-Identifier: Apache-2.0

from sqlalchemy import sql

from warehouse.ip_addresses.models import BanReason

from ...common.db.ip_addresses import IpAddressFactory


class TestAdminFlag:
    def test_no_ip_not_banned(self, db_request):
        assert not db_request.banned.by_ip("192.0.2.4")

    def test_with_ip_not_banned(self, db_request):
        assert not db_request.banned.by_ip(db_request.ip_address.ip_address)

    def test_with_ip_banned(self, db_request, user_service, mocker):
        mocker.spy(user_service, "_hit_ratelimits")
        mocker.spy(user_service, "_check_ratelimits")
        ip_addy = IpAddressFactory(
            is_banned=True,
            ban_reason=BanReason.AUTHENTICATION_ATTEMPTS,
            ban_date=sql.func.now(),
        )
        assert db_request.banned.by_ip(ip_addy.ip_address)
        user_service._hit_ratelimits.assert_called_once_with(userid=None)
        user_service._check_ratelimits.assert_called_once_with(
            userid=None, tags=["banned:by_ip"]
        )
