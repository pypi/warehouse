# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from warehouse.accounts.models import Email
from warehouse.accounts.services import IDomainStatusService

if TYPE_CHECKING:
    from pyramid.request import Request

    from warehouse.accounts.models import User
    from warehouse.macaroons.models import Macaroon


@dataclass
class UserContext:
    """
    This class supports `MacaroonSecurityPolicy` in
    `warehouse.macaroons.security_policy`.

    It is a wrapper containing both a user associated with an authenticated request
    and an optional corresponding Macaroon, if the authentication was via API token.
    If the request was authenticated via login session, `macaroon` should be None.
    """

    user: User
    """
    The associated user.
    """

    macaroon: Macaroon | None
    """
    The Macaroon associated to the API token used to authenticate, if token
    authentication was used.
    """

    def __principals__(self) -> list[str]:
        return self.user.__principals__()


def update_email_domain_status(email: Email, request: Request) -> None:
    """
    Update the domain status of the given email address.
    """
    domain_status_service = request.find_service(IDomainStatusService)

    if domain_status := domain_status_service.get_domain_status(email.domain):
        # Success: update timestamp to now, won't be checked again for 30 days
        email.domain_last_checked = datetime.now(UTC)
        email.domain_last_status = domain_status
    else:
        # Failure: set timestamp so we retry in ~7 days instead of 30
        # (task selects emails where domain_last_checked < now - 30 days)
        email.domain_last_checked = datetime.now(UTC) - timedelta(days=23)
    request.db.add(email)

    return None
