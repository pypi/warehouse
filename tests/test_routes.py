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

from warehouse.routes import includeme


def test_routes():
    class FakeConfig:

        def __init__(self):
            self.routes = []

        def add_route(self, *args):
            self.routes.append(args)

    config = FakeConfig()
    includeme(config)

    assert config.routes == [
        ("accounts.profile", "/user/{username}/"),
        ("accounts.login", "/account/login/"),
        ("accounts.logout", "/account/logout/"),
    ]
