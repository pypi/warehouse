# SPDX-License-Identifier: Apache-2.0

import psycopg
import pytest

from sqlalchemy import sql

from warehouse.ip_addresses.models import BanReason

from ...common.constants import REMOTE_ADDR
from ...common.db.ip_addresses import IpAddressFactory as DBIpAddressFactory


class TestIpAddress:
    def test_repr(self, db_request):
        ip_address = db_request.ip_address
        assert isinstance(repr(ip_address), str)
        assert repr(ip_address) == REMOTE_ADDR

    def test_invalid_transformed(self, db_request):
        ip_address = DBIpAddressFactory(ip_address="wutang")
        assert repr(ip_address) == "192.0.2.69"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"ip_address": REMOTE_ADDR, "is_banned": True},
            {
                "ip_address": REMOTE_ADDR,
                "is_banned": True,
                "ban_reason": BanReason.AUTHENTICATION_ATTEMPTS,
            },
            {"ip_address": REMOTE_ADDR, "is_banned": True, "ban_date": sql.func.now()},
            {
                "ip_address": REMOTE_ADDR,
                "is_banned": False,
                "ban_reason": BanReason.AUTHENTICATION_ATTEMPTS,
            },
            {"ip_address": REMOTE_ADDR, "is_banned": False, "ban_date": sql.func.now()},
            {
                "ip_address": REMOTE_ADDR,
                "is_banned": False,
                "ban_reason": BanReason.AUTHENTICATION_ATTEMPTS,
                "ban_date": sql.func.now(),
            },
        ],
    )
    def test_ban_data_constraint(self, db_request, kwargs):
        with pytest.raises(psycopg.errors.CheckViolation):
            DBIpAddressFactory(**kwargs)
