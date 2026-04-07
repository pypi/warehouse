# SPDX-License-Identifier: Apache-2.0

import pretend

from celery.schedules import crontab
from sqlalchemy import true

from warehouse import sponsors
from warehouse.sponsors.models import Sponsor
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
        pretend.call(
            sponsors._footer_sponsors, name="footer_sponsors", reify=True
        ),
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
        pretend.call(
            sponsors._footer_sponsors, name="footer_sponsors", reify=True
        ),
    ]
    assert not config.add_periodic_task.calls


def test_list_sponsors(db_request):
    SponsorFactory.create_batch(5)
    SponsorFactory.create_batch(3, is_active=False)

    result = sponsors._sponsors(db_request)
    expected = (
        db_request.db.query(Sponsor)
        .filter(Sponsor.is_active == true())
        .all()
    )

    assert result == expected
    assert len(result) == 5


def test_footer_sponsors_ordering(db_request):
    c = SponsorFactory.create
    infra = c(name="AWS", infra_sponsor=True, footer=False, level_order=0)
    vis_b = c(name="Bravo", footer=True, infra_sponsor=False, level_order=1)
    vis_a = c(name="Alpha", footer=True, infra_sponsor=False, level_order=1)
    sus = c(name="Charlie", footer=True, infra_sponsor=False, level_order=2)
    c(name="Nobody", footer=False, infra_sponsor=False, level_order=5)

    db_request.sponsors = sponsors._sponsors(db_request)
    assert sponsors._footer_sponsors(db_request) == [vis_a, vis_b, sus, infra]
