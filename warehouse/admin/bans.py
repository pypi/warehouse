# SPDX-License-Identifier: Apache-2.0

from sqlalchemy import type_coerce
from sqlalchemy.dialects.postgresql import INET

from warehouse.accounts.interfaces import IUserService
from warehouse.events.models import IpAddress


class Bans:
    def __init__(self, request):
        self.request = request

    def by_ip(self, ip_address: str) -> bool:
        banned = (
            self.request.db.query(IpAddress)
            .filter_by(ip_address=type_coerce(ip_address, INET), is_banned=True)
            .one_or_none()
        )
        if banned is not None:
            login_service = self.request.find_service(IUserService, context=None)
            login_service._check_ratelimits(userid=None, tags=["banned:by_ip"])
            login_service._hit_ratelimits(userid=None)
            return True

        return False


def includeme(config):
    config.add_request_method(Bans, name="banned", reify=True)
