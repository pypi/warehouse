# SPDX-License-Identifier: Apache-2.0

from urllib.parse import urlencode

import pretend
import pytest

from requests.exceptions import HTTPError

from warehouse.sponsors import tasks
from warehouse.sponsors.models import Sponsor

from ...common.db.sponsors import SponsorFactory


@pytest.fixture
def fake_task_request():
    cfg = {
        "pythondotorg.host": "https://API_HOST",
        "pythondotorg.api_token": "API_TOKEN",
    }
    request = pretend.stub(registry=pretend.stub(settings=cfg))
    return request


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


def test_create_new_sponsor_if_no_matching(
    monkeypatch, db_request, fake_task_request, sponsor_api_data
):
    response = pretend.stub(
        raise_for_status=lambda: None, json=lambda: sponsor_api_data
    )
    requests = pretend.stub(
        get=pretend.call_recorder(lambda url, headers, timeout: response)
    )
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


def test_update_remote_sponsor_with_same_name_with_new_logo(
    monkeypatch, db_request, fake_task_request, sponsor_api_data
):
    response = pretend.stub(
        raise_for_status=lambda: None, json=lambda: sponsor_api_data
    )
    requests = pretend.stub(
        get=pretend.call_recorder(lambda url, headers, timeout: response)
    )
    monkeypatch.setattr(tasks, "requests", requests)
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

    assert 1 == len(db_request.db.query(Sponsor).all())
    db_sponsor = db_request.db.query(Sponsor).one()
    assert db_sponsor.id == created_sponsor.id
    assert "sponsor-name" == db_sponsor.slug
    assert "Sponsor description" == db_sponsor.service
    assert "https://sponsor.example.com/" == db_sponsor.link_url
    assert "https://logourl.com" == db_sponsor.color_logo_url
    assert db_sponsor.activity_markdown is created_sponsor.activity_markdown
    assert db_sponsor.white_logo_url is created_sponsor.white_logo_url
    assert db_sponsor.is_active is True
    assert db_sponsor.psf_sponsor is True
    assert db_sponsor.footer is False
    assert db_sponsor.infra_sponsor is False
    assert db_sponsor.one_time is False
    assert db_sponsor.sidebar is False
    assert "remote" == db_sponsor.origin
    assert "Partner" == db_sponsor.level_name
    assert 5 == db_sponsor.level_order


def test_do_not_update_if_not_psf_sponsor(
    monkeypatch, db_request, fake_task_request, sponsor_api_data
):
    response = pretend.stub(
        raise_for_status=lambda: None, json=lambda: sponsor_api_data
    )
    requests = pretend.stub(
        get=pretend.call_recorder(lambda url, headers, timeout: response)
    )
    monkeypatch.setattr(tasks, "requests", requests)
    infra_sponsor = SponsorFactory.create(
        name=sponsor_api_data[0]["sponsor"],
        psf_sponsor=False,
        infra_sponsor=True,
        one_time=False,
        origin="manual",
    )

    fake_task_request.db = db_request.db
    tasks.update_pypi_sponsors(fake_task_request)

    assert 1 == len(db_request.db.query(Sponsor).all())
    db_sponsor = db_request.db.query(Sponsor).one()
    assert db_sponsor.id == infra_sponsor.id
    assert "manual" == db_sponsor.origin
    assert "sponsor-name" != db_sponsor.slug


def test_update_remote_sponsor_with_same_slug_with_new_logo(
    monkeypatch, db_request, fake_task_request, sponsor_api_data
):
    response = pretend.stub(
        raise_for_status=lambda: None, json=lambda: sponsor_api_data
    )
    requests = pretend.stub(
        get=pretend.call_recorder(lambda url, headers, timeout: response)
    )
    monkeypatch.setattr(tasks, "requests", requests)
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

    assert 1 == len(db_request.db.query(Sponsor).all())
    db_sponsor = db_request.db.query(Sponsor).one()
    assert db_sponsor.id == created_sponsor.id
    assert "Sponsor Name" == db_sponsor.name
    assert "Sponsor description" == db_sponsor.service


def test_flag_existing_psf_sponsor_to_false_if_not_present_in_api_response(
    monkeypatch, db_request, fake_task_request, sponsor_api_data
):
    response = pretend.stub(
        raise_for_status=lambda: None, json=lambda: sponsor_api_data
    )
    requests = pretend.stub(
        get=pretend.call_recorder(lambda url, headers, timeout: response)
    )
    monkeypatch.setattr(tasks, "requests", requests)
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

    assert 2 == len(db_request.db.query(Sponsor).all())
    created_sponsor = (
        db_request.db.query(Sponsor).filter(Sponsor.id == created_sponsor.id).one()
    )
    # no longer PSF sponsor but stay active as sidebar/footer sponsor
    assert created_sponsor.psf_sponsor is False
    assert created_sponsor.sidebar is True
    assert created_sponsor.footer is True
    assert created_sponsor.is_active is True
