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

from warehouse.events.models import IpAddress


class Bans:
    def __init__(self, request):
        self.request = request

    def by_ip(self, ip_address):
        banned = (
            self.request.db.query(IpAddress)
            .filter_by(ip_address=ip_address, is_banned=True)
            .one_or_none()
        )
        return True if banned is not None else False


def includeme(config):
    config.add_request_method(Bans, name="banned", reify=True)
