# SPDX-License-Identifier: Apache-2.0

from celery.schedules import crontab
from sqlalchemy import true

from warehouse.sponsors.models import Sponsor
from warehouse.sponsors.tasks import update_pypi_sponsors


def _sponsors(request):
    """Return active sponsors grouped and ordered for template rendering."""
    sponsors = (
        request.db.query(Sponsor)
        .filter(Sponsor.is_active == true())
        .order_by(Sponsor.level_order, Sponsor.name)
        .all()
    )
    infrastructure = [s for s in sponsors if s.infra_sponsor]
    return {
        "all": sponsors,
        "psf": [s for s in sponsors if s.psf_sponsor],
        "infrastructure": infrastructure,
        "one_time": [s for s in sponsors if s.one_time],
        "footer": [s for s in sponsors if s.footer and not s.infra_sponsor]
        + infrastructure,
    }


def includeme(config):
    # Add a request method which will allow to list sponsors
    config.add_request_method(_sponsors, name="sponsors", reify=True)

    # Add a periodic task to update sponsors table
    if config.registry.settings.get("pythondotorg.api_token"):
        config.add_periodic_task(crontab(minute=10), update_pypi_sponsors)
