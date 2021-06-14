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

from sqlalchemy import true

from warehouse import sponsors
from warehouse.sponsors.models import Sponsor

from ...common.db.sponsors import SponsorFactory


def test_includeme():
    config = pretend.stub(
        add_request_method=pretend.call_recorder(lambda f, name, reify: None)
    )

    sponsors.includeme(config)

    assert config.add_request_method.calls == [
        pretend.call(sponsors._sponsors, name="sponsors", reify=True),
    ]


def test_list_sponsors(db_request):
    [SponsorFactory.create() for i in range(5)]
    [SponsorFactory.create(is_active=False) for i in range(3)]

    result = sponsors._sponsors(db_request)
    expected = db_request.db.query(Sponsor).filter(Sponsor.is_active == true()).all()

    assert result == expected
    assert len(result) == 5
