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
import pytest

from celery.schedules import crontab

from warehouse import credits
from warehouse.credits.tasks import get_contributors


@pytest.mark.parametrize("with_github_access_token", [True, False])
def test_includeme(with_github_access_token):

    config = pretend.stub(
        get_settings=lambda: (
            {"warehouse.github_access_token": "foobar"}
            if with_github_access_token
            else {}
        ),
        add_periodic_task=pretend.call_recorder(lambda *a, **kw: None),
    )

    credits.includeme(config)

    if with_github_access_token:
        assert config.add_periodic_task.calls == [
            pretend.call(crontab(minute=2, hour=2), get_contributors)
        ]
