# SPDX-License-Identifier: Apache-2.0

from urllib.parse import parse_qs, urlencode

import pretend
import pytest

from requests.exceptions import HTTPError
from urllib3.util import parse_url

from warehouse.sponsors import tasks
from warehouse.sponsors.models import Sponsor

from ...common.db.sponsors import SponsorFactory


@pytest.fixture
def fake_task_request():
    cfg = {
        "pythondotorg.host": "https://API_HOST",
        "pythondotorg.api_token": "API_TOKEN",
    }
    return pretend.stub(registry=pretend.stub(settings=cfg))


@pytest.fixture
def sponsor_api_data():
    return [
        {
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
            "level_order": 5,
        }
    ]


@pytest.fixture
def fake_requests(monkeypatch, sponsor_api_data):
    """Stub ``requests.get`` so each flight gets its own payload."""
    payloads = {"sponsors": sponsor_api_data, "sidebar": []}

    def get(url, headers, timeout):
        flight = parse_qs(parse_url(url).query)["flight"][0]
        return pretend.stub(
            raise_for_status=lambda: None, json=lambda: payloads[flight]
        )

    requests = pretend.stub(get=pretend.call_recorder(get), payloads=payloads)
    monkeypatch.setattr(tasks, "requests", requests)
    return requests


def test_raise_error_if_invalid_response(monkeypatch, db_request, fake_task_request):
    response = pretend.stub(
        status_code=418,
        text="I'm a teapot",
        raise_for_status=pretend.raiser(HTTPError),
    )
    requests = pretend.stub(
        get=pretend.call_recorder(lambda url, headers, timeout: response)
    )
    monkeypatch.setattr(tasks, "requests", requests)

    with pytest.raises(HTTPError):
        tasks.update_pypi_sponsors(fake_task_request)

    qs = urlencode({"publisher": "pypi", "flight": "sponsors"})
    headers = {"Authorization": "Token API_TOKEN"}
    expected_url = f"https://API_HOST/api/v2/sponsors/logo-placement/?{qs}"
    assert requests.get.calls == [
        pretend.call(expected_url, headers=headers, timeout=5)
    ]


def test_fetches_sponsors_and_sidebar_flights(
    db_request, fake_task_request, fake_requests
):
    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    headers = {"Authorization": "Token API_TOKEN"}
    base_url = "https://API_HOST/api/v2/sponsors/logo-placement/?"
    assert fake_requests.get.calls == [
        pretend.call(
            base_url + urlencode({"publisher": "pypi", "flight": "sponsors"}),
            headers=headers,
            timeout=5,
        ),
        pretend.call(
            base_url + urlencode({"publisher": "pypi", "flight": "sidebar"}),
            headers=headers,
            timeout=5,
        ),
    ]


def test_create_new_sponsor_if_no_matching(
    db_request, fake_task_request, sponsor_api_data, fake_requests
):
    assert len(db_request.db.query(Sponsor).all()) == 0

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    db_sponsor = db_request.db.query(Sponsor).one()
    assert db_sponsor.slug == "sponsor-name"
    assert db_sponsor.name == "Sponsor Name"
    assert db_sponsor.service == "Sponsor description"
    assert db_sponsor.link_url == "https://sponsor.example.com/"
    assert db_sponsor.color_logo_url == "https://logourl.com"
    assert db_sponsor.activity_markdown is None
    assert db_sponsor.white_logo_url is None
    assert db_sponsor.is_active is True
    assert db_sponsor.psf_sponsor is True
    assert db_sponsor.footer is False
    assert db_sponsor.infra_sponsor is False
    assert db_sponsor.one_time is False
    assert db_sponsor.sidebar is False
    assert db_sponsor.origin == "remote"
    assert db_sponsor.level_name == "Partner"
    assert db_sponsor.level_order == 5


def test_update_remote_sponsor_with_same_name_with_new_logo(
    db_request, fake_task_request, sponsor_api_data, fake_requests
):
    created_sponsor = SponsorFactory.create(
        name=sponsor_api_data[0]["sponsor"],
        psf_sponsor=True,
        footer=False,
        sidebar=False,
        one_time=False,
        origin="manual",
    )

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    assert len(db_request.db.query(Sponsor).all()) == 1
    db_sponsor = db_request.db.query(Sponsor).one()
    assert db_sponsor.id == created_sponsor.id
    assert db_sponsor.slug == "sponsor-name"
    assert db_sponsor.service == "Sponsor description"
    assert db_sponsor.link_url == "https://sponsor.example.com/"
    assert db_sponsor.color_logo_url == "https://logourl.com"
    assert db_sponsor.activity_markdown is created_sponsor.activity_markdown
    assert db_sponsor.white_logo_url is created_sponsor.white_logo_url
    assert db_sponsor.is_active is True
    assert db_sponsor.psf_sponsor is True
    assert db_sponsor.footer is False
    assert db_sponsor.infra_sponsor is False
    assert db_sponsor.one_time is False
    assert db_sponsor.sidebar is False
    assert db_sponsor.origin == "remote"
    assert db_sponsor.level_name == "Partner"
    assert db_sponsor.level_order == 5


def test_do_not_update_if_not_psf_sponsor(
    db_request, fake_task_request, sponsor_api_data, fake_requests
):
    infra_sponsor = SponsorFactory.create(
        name=sponsor_api_data[0]["sponsor"],
        psf_sponsor=False,
        infra_sponsor=True,
        one_time=False,
        origin="manual",
    )

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    assert len(db_request.db.query(Sponsor).all()) == 1
    db_sponsor = db_request.db.query(Sponsor).one()
    assert db_sponsor.id == infra_sponsor.id
    assert db_sponsor.origin == "manual"
    assert db_sponsor.slug != "sponsor-name"


def test_update_remote_sponsor_with_same_slug_with_new_logo(
    db_request, fake_task_request, sponsor_api_data, fake_requests
):
    created_sponsor = SponsorFactory.create(
        slug=sponsor_api_data[0]["sponsor_slug"],
        psf_sponsor=True,
        footer=False,
        sidebar=False,
        one_time=False,
        origin="manual",
    )

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    assert len(db_request.db.query(Sponsor).all()) == 1
    db_sponsor = db_request.db.query(Sponsor).one()
    assert db_sponsor.id == created_sponsor.id
    assert db_sponsor.name == "Sponsor Name"
    assert db_sponsor.service == "Sponsor description"


@pytest.mark.parametrize(
    ("level_name", "expected_footer"),
    [
        ("Visionary", True),
        ("Sustainability", True),
        ("Partner", False),
    ],
)
def test_footer_set_based_on_level(
    db_request,
    fake_task_request,
    sponsor_api_data,
    fake_requests,
    level_name,
    expected_footer,
):
    sponsor_api_data[0]["level_name"] = level_name

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    db_sponsor = db_request.db.query(Sponsor).one()
    assert db_sponsor.footer is expected_footer


def test_white_logo_synced_when_provided(
    db_request, fake_task_request, sponsor_api_data, fake_requests
):
    sponsor_api_data[0]["white_logo"] = "https://logourl.com/white.png"

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    assert (
        db_request.db.query(Sponsor).one().white_logo_url
        == "https://logourl.com/white.png"
    )


def test_flag_existing_psf_sponsor_to_false_if_not_present_in_api_response(
    db_request, fake_task_request, sponsor_api_data, fake_requests
):
    created_sponsor = SponsorFactory.create(
        slug="other-slug",
        name="Other Sponsor",
        psf_sponsor=True,
        footer=True,
        sidebar=True,
        origin="manual",
    )

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    assert len(db_request.db.query(Sponsor).all()) == 2
    created_sponsor = (
        db_request.db.query(Sponsor).filter(Sponsor.id == created_sponsor.id).one()
    )
    # no longer PSF sponsor but stay active as sidebar/footer sponsor
    assert created_sponsor.psf_sponsor is False
    assert created_sponsor.sidebar is True
    assert created_sponsor.footer is True
    assert created_sponsor.is_active is True


def test_sidebar_flag_set_from_sidebar_flight(
    db_request, fake_task_request, sponsor_api_data, fake_requests
):
    fake_requests.payloads["sidebar"] = [sponsor_api_data[0]]

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    db_sponsor = db_request.db.query(Sponsor).one()
    assert db_sponsor.psf_sponsor is True
    assert db_sponsor.sidebar is True


def test_sidebar_only_sponsor_is_created(
    db_request, fake_task_request, sponsor_api_data, fake_requests
):
    fake_requests.payloads["sponsors"] = []
    fake_requests.payloads["sidebar"] = [sponsor_api_data[0]]

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    db_sponsor = db_request.db.query(Sponsor).one()
    assert db_sponsor.slug == "sponsor-name"
    assert db_sponsor.service == "Sponsor description"
    assert db_sponsor.color_logo_url == "https://logourl.com"
    assert db_sponsor.is_active is True
    assert db_sponsor.origin == "remote"
    assert db_sponsor.sidebar is True
    assert db_sponsor.psf_sponsor is False
    assert db_sponsor.footer is False


def test_sidebar_flag_cleared_for_remote_sponsor_absent_from_sidebar_flight(
    db_request, fake_task_request, sponsor_api_data, fake_requests
):
    SponsorFactory.create(
        slug=sponsor_api_data[0]["sponsor_slug"],
        name=sponsor_api_data[0]["sponsor"],
        sidebar=True,
        origin="remote",
    )

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    db_sponsor = db_request.db.query(Sponsor).one()
    assert db_sponsor.psf_sponsor is True
    assert db_sponsor.sidebar is False
