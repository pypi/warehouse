# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.dialects.postgresql import insert as pg_insert
from tldextract import TLDExtract

from warehouse.accounts.models import Email, ProhibitedEmailDomain
from warehouse.accounts.services import IDomainStatusService

if TYPE_CHECKING:
    from pyramid.request import Request
    from sqlalchemy.orm import Session

    from warehouse.accounts.models import User
    from warehouse.macaroons.models import Macaroon

tld_extractor = TLDExtract(suffix_list_urls=())  # Updated during image build


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


def prohibit_email_domain(
    db: Session,
    domain: str,
    *,
    comment: str = "",
    prohibited_by: User | None = None,
    is_mx_record: bool = False,
) -> bool:
    """
    Add a domain to the prohibited email domains blocklist.

    Refuses an empty domain: a domain='' row would match every address
    whose host has no registrable domain, and the admin UI has no way to
    delete it.

    Returns False without changing anything when an entry for the domain
    already exists, whatever its is_mx_record flag: the domain column is
    unique. ON CONFLICT closes the race between concurrent first uses of
    the same domain, which a check-then-insert would lose (cf. the same
    idiom in warehouse/utils/wsgi.py).
    """
    if not domain:
        return False

    inserted_id = db.execute(
        pg_insert(ProhibitedEmailDomain)
        .values(
            domain=domain,
            comment=comment,
            _prohibited_by=prohibited_by.id if prohibited_by else None,
            is_mx_record=is_mx_record,
        )
        .on_conflict_do_nothing(index_elements=["domain"])
        .returning(ProhibitedEmailDomain.id)
    ).scalar_one_or_none()
    return inserted_id is not None


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
