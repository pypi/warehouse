# SPDX-License-Identifier: Apache-2.0

import pretend

from celery.schedules import crontab

from warehouse import sponsors
from warehouse.sponsors.tasks import update_pypi_sponsors

from ...common.db.sponsors import SponsorFactory


def test_includeme():
    settings = {"pythondotorg.api_token": "test-token"}
    config = pretend.stub(
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        add_periodic_task=pretend.call_recorder(lambda crontab, task: None),
        registry=pretend.stub(settings=settings),
    )

    sponsors.includeme(config)

    assert config.add_request_method.calls == [
        pretend.call(sponsors._sponsors, name="sponsors", reify=True),
    ]
    assert config.add_periodic_task.calls == [
        pretend.call(crontab(minute=10), update_pypi_sponsors),
    ]


def test_do_not_schedule_sponsor_api_integration_if_no_token():
    settings = {}
    config = pretend.stub(
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        add_periodic_task=pretend.call_recorder(lambda crontab, task: None),
        registry=pretend.stub(settings=settings),
    )

    sponsors.includeme(config)

    assert config.add_request_method.calls == [
        pretend.call(sponsors._sponsors, name="sponsors", reify=True),
    ]
    assert not config.add_periodic_task.calls


def test_list_sponsors(db_request):
    expected = SponsorFactory.create_batch(5)
    SponsorFactory.create_batch(3, is_active=False)

    result = sponsors._sponsors(db_request)

    assert len(result["all"]) == 5
    assert set(result["all"]) == set(expected)


def test_sponsors_grouped_and_ordered(db_request):
    c = SponsorFactory.create
    infra = c(name="AWS", infra_sponsor=True, psf_sponsor=False, level_order=0)
    vis_b = c(name="Bravo", psf_sponsor=True, infra_sponsor=False, level_order=1)
    vis_a = c(name="Alpha", psf_sponsor=True, infra_sponsor=False, level_order=1)
    sus = c(name="Charlie", psf_sponsor=True, infra_sponsor=False, level_order=2)
    onetime = c(name="Delta", psf_sponsor=False, one_time=True, level_order=3)

    result = sponsors._sponsors(db_request)

    assert result["all"] == [infra, vis_a, vis_b, sus, onetime]
    assert result["psf"] == [vis_a, vis_b, sus]
    assert result["infrastructure"] == [infra]
    assert result["one_time"] == [onetime]


def test_footer_sponsors_ordering(db_request):
    c = SponsorFactory.create
    infra = c(
        name="AWS", infra_sponsor=True, psf_sponsor=False, footer=False, level_order=0
    )
    vis_b = c(name="Bravo", footer=True, infra_sponsor=False, level_order=1)
    vis_a = c(name="Alpha", footer=True, infra_sponsor=False, level_order=1)
    sus = c(name="Charlie", footer=True, infra_sponsor=False, level_order=2)
    c(name="Nobody", footer=False, infra_sponsor=False, level_order=5)

    result = sponsors._sponsors(db_request)

    assert result["footer"] == [vis_a, vis_b, sus, infra]
