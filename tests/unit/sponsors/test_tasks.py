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
from warehouse.sponsors.models import Sponsor


@pytest.fixture
def fake_task_request():
    cfg = {"pythondotorg.host": "API_HOST", "pythondotorg.api_token": "API_TOKEN"}
    request = pretend.stub(registry=pretend.stub(settings=cfg))
    return request

@pytest.fixture
def sponsor_api_data():
    return [{
      "publisher": "pypi",
      "flight": "sponsors",
      "sponsor": "Sponsor Name",
      "sponsor_slug": "sponsor-name",
      "description": "Sponsor description",
      "logo": "https://logourl.com",
      "start_date": "2021-02-17",
      "end_date": "2022-02-17",
      "sponsor_url": "https://sponsor.example.com/",
      "level_name": "Partner",
      "level_order": 5
    }]


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

def test_create_new_sponsor_if_no_matching(monkeypatch, db_request, fake_task_request, sponsor_api_data):
    response = pretend.stub(raise_for_status=lambda: None, json=lambda: sponsor_api_data)
    requests = pretend.stub(get=pretend.call_recorder(lambda url, headers: response))
    monkeypatch.setattr(tasks, "requests", requests)
    assert 0 == len(db_request.db.query(Sponsor).all())

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    db_sponsor = db_request.db.query(Sponsor).one()
    assert "sponsor-name" == db_sponsor.slug
    assert "Sponsor Name" == db_sponsor.name
    assert "Sponsor description" == db_sponsor.service
    assert "https://sponsor.example.com/" == db_sponsor.link_url
    assert "https://logourl.com" == db_sponsor.color_logo_url
    assert db_sponsor.activity_markdown is None
    assert db_sponsor.white_logo_url is None
    assert db_sponsor.is_active is True
    assert db_sponsor.psf_sponsor is True
    assert db_sponsor.footer is False
    assert db_sponsor.infra_sponsor is False
    assert db_sponsor.one_time is False
    assert db_sponsor.sidebar is False
    assert "remote" == db_sponsor.origin
    assert "Partner" == db_sponsor.level_name
    assert 5 == db_sponsor.level_order
