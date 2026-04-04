# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import typing

from celery.schedules import crontab

from warehouse.oidc.interfaces import IOIDCPublisherService
from warehouse.oidc.services import OIDCPublisherServiceFactory
from warehouse.oidc.tasks import compute_oidc_metrics, delete_expired_oidc_macaroons
from warehouse.oidc.utils import (
    ACTIVESTATE_OIDC_ISSUER_URL,
    CIRCLECI_OIDC_ISSUER_URL,
    GITHUB_OIDC_ISSUER_URL,
    GITLAB_OIDC_ISSUER_URL,
    GOOGLE_OIDC_ISSUER_URL,
)

if typing.TYPE_CHECKING:
    from pyramid.config import Configurator


def includeme(config: Configurator) -> None:
    oidc_publisher_service_class = config.maybe_dotted(
        config.registry.settings["oidc.backend"]
    )

    config.register_service_factory(
        OIDCPublisherServiceFactory(
            publisher="github",
            issuer_url=GITHUB_OIDC_ISSUER_URL,
            service_class=oidc_publisher_service_class,
        ),
        IOIDCPublisherService,
        name="github",
    )
    config.register_service_factory(
        OIDCPublisherServiceFactory(
            publisher="gitlab",
            issuer_url=GITLAB_OIDC_ISSUER_URL,
            service_class=oidc_publisher_service_class,
        ),
        IOIDCPublisherService,
        name="gitlab",
    )
    config.register_service_factory(
        OIDCPublisherServiceFactory(
            publisher="google",
            issuer_url=GOOGLE_OIDC_ISSUER_URL,
            service_class=oidc_publisher_service_class,
        ),
        IOIDCPublisherService,
        name="google",
    )

    config.register_service_factory(
        OIDCPublisherServiceFactory(
            publisher="activestate",
            issuer_url=ACTIVESTATE_OIDC_ISSUER_URL,
            service_class=oidc_publisher_service_class,
        ),
        IOIDCPublisherService,
        name="activestate",
    )

    config.register_service_factory(
        OIDCPublisherServiceFactory(
            publisher="circleci",
            issuer_url=CIRCLECI_OIDC_ISSUER_URL,
            service_class=oidc_publisher_service_class,
        ),
        IOIDCPublisherService,
        name="circleci",
    )

    # During deployments, we separate auth routes into their own subdomain
    # to simplify caching exclusion.
    auth = config.get_settings().get("auth.domain")

    config.add_route("oidc.audience", "/_/oidc/audience", domain=auth)
    config.add_route("oidc.mint_token", "/_/oidc/mint-token", domain=auth)
    # NOTE: This is a legacy route for the above. Pyramid requires route
    # names to be unique, so we can't deduplicate it.
    config.add_route("oidc.github.mint_token", "/_/oidc/github/mint-token", domain=auth)

    # Compute OIDC metrics periodically
    config.add_periodic_task(crontab(minute=0, hour="*"), compute_oidc_metrics)

    # Daily purge expired OIDC-minted API tokens. These tokens are temporary in nature
    # and expire after 15 minutes of creation.
    config.add_periodic_task(crontab(minute=0, hour=6), delete_expired_oidc_macaroons)
