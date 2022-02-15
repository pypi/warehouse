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
from urllib.parse import urlencode
from requests.exceptions import HTTPError

import pretend
import pytest

from warehouse.sponsors import tasks


@pytest.fixture
def fake_task_request():
    cfg = {"pythondotorg.host": "API_HOST", "pythondotorg.api_token": "API_TOKEN"}
    request = pretend.stub(registry=pretend.stub(settings=cfg))
    return request


def test_raise_error_if_invalid_response(monkeypatch, db_request, fake_task_request):
    response = pretend.stub(
        status_code=418,
        text="I'm a teapot",
        raise_for_status=pretend.raiser(HTTPError),
    )
    requests = pretend.stub(get=pretend.call_recorder(lambda url, headers: response))
    monkeypatch.setattr(tasks, "requests", requests)

    with pytest.raises(HTTPError):
        tasks.update_pypi_sponsors(fake_task_request)

    qs = urlencode({"publisher": "pypi", "flight": "sponsors"})
    headers = {"Authorization": "Token API_TOKEN"}
    expected_url = f"https://API_HOST/api/v2/sponsors/logo-placement/?{qs}"
    assert requests.get.calls == [pretend.call(expected_url, headers=headers)]
