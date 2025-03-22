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

from warehouse import banners


def test_includeme():
    config = pretend.stub(
        get_settings=lambda: {"warehouse.domain": "pypi"},
        add_route=pretend.call_recorder(lambda name, route, domain: None),
    )

    banners.includeme(config)

    assert config.add_route.calls == [
        pretend.call(
            "includes.db-banners",
            "/_includes/unauthed/notification-banners/",
            domain="pypi",
        ),
    ]
