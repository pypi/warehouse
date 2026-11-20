# SPDX-License-Identifier: Apache-2.0

import pytest

from celery.schedules import crontab

from warehouse import sponsors, tasks
from warehouse.sponsors.tasks import update_pypi_sponsors

from ...common.db.sponsors import SponsorFactory


@pytest.fixture
def add_periodic_task(mocker, pyramid_config):
    """Register an autospec of the ``add_periodic_task`` directive."""
    directive = mocker.create_autospec(tasks._add_periodic_task)
    pyramid_config.add_directive("add_periodic_task", directive, action_wrap=False)
    return directive


def test_includeme(mocker, pyramid_config, add_periodic_task):
    pyramid_config.registry.settings["pythondotorg.api_token"] = "test-token"
    add_request_method = mocker.spy(pyramid_config, "add_request_method")

    sponsors.includeme(pyramid_config)

    add_request_method.assert_called_once_with(
        sponsors._sponsors, name="sponsors", reify=True
    )
    add_periodic_task.assert_called_once_with(
        pyramid_config, crontab(minute=10), update_pypi_sponsors
    )


def test_do_not_schedule_sponsor_api_integration_if_no_token(
    mocker, pyramid_config, add_periodic_task
):
    add_request_method = mocker.spy(pyramid_config, "add_request_method")

    sponsors.includeme(pyramid_config)

    add_request_method.assert_called_once_with(
        sponsors._sponsors, name="sponsors", reify=True
    )
    add_periodic_task.assert_not_called()


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


def test_footer_grouped_by_tier(db_request):
    c = SponsorFactory.create
    infra = c(
        name="AWS", infra_sponsor=True, psf_sponsor=False, footer=False, level_order=0
    )
    vis_b = c(
        name="Bravo",
        footer=True,
        infra_sponsor=False,
        level_name="Visionary",
        level_order=1,
    )
    vis_a = c(
        name="Alpha",
        footer=True,
        infra_sponsor=False,
        level_name="Visionary",
        level_order=1,
    )
    sus = c(
        name="Charlie",
        footer=True,
        infra_sponsor=False,
        level_name="Sustainability",
        level_order=2,
    )
    c(name="Nobody", footer=False, infra_sponsor=False, level_order=5)

    result = sponsors._sponsors(db_request)

    # PSF sponsors grouped by tier in level order, then infrastructure last
    # (tier=None). The footer template renders each group's heading.
    assert result["footer"] == [
        {"tier": "Visionary", "sponsors": [vis_a, vis_b]},
        {"tier": "Sustainability", "sponsors": [sus]},
        {"tier": None, "sponsors": [infra]},
    ]
