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
