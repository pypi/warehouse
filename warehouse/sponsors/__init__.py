# SPDX-License-Identifier: Apache-2.0

from celery.schedules import crontab
from sqlalchemy import true

from warehouse.sponsors.models import Sponsor
from warehouse.sponsors.tasks import update_pypi_sponsors


def _sponsors(request):
    return request.db.query(Sponsor).filter(Sponsor.is_active == true()).all()


def _footer_sponsors(request):
    """Return footer sponsors: PSF by level then name, infra by name."""
    all_sponsors = request.sponsors
    psf = sorted(
        (s for s in all_sponsors if s.footer and not s.infra_sponsor),
        key=lambda s: (s.level_order or 0, s.name),
    )
    infra = sorted(
        (s for s in all_sponsors if s.infra_sponsor),
        key=lambda s: s.name,
    )
    return psf + infra


def includeme(config):
    # Add a request method which will allow to list sponsors
    config.add_request_method(_sponsors, name="sponsors", reify=True)
    config.add_request_method(_footer_sponsors, name="footer_sponsors", reify=True)

    # Add a periodic task to update sponsors table
    if config.registry.settings.get("pythondotorg.api_token"):
        config.add_periodic_task(crontab(minute=10), update_pypi_sponsors)
