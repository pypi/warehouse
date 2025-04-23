# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import typing

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import func, nullsfirst, or_, select

from warehouse import tasks
from warehouse.accounts.models import (
    Email,
    TermsOfServiceEngagement,
    User,
    UserTermsOfServiceEngagement,
)
from warehouse.accounts.services import IUserService
from warehouse.accounts.utils import update_email_domain_status
from warehouse.email import send_user_terms_of_service_updated
from warehouse.metrics import IMetricsService
from warehouse.packaging.models import Release

if typing.TYPE_CHECKING:
    from pyramid.request import Request


@tasks.task(ignore_result=True, acks_late=True)
def notify_users_of_tos_update(request):
    user_service = request.find_service(IUserService, context=None)
    already_notified_subquery = (
        request.db.query(UserTermsOfServiceEngagement.user_id)
        .filter(
            UserTermsOfServiceEngagement.revision
            == request.registry.settings.get("terms.revision")
        )
        .filter(
            UserTermsOfServiceEngagement.engagement.in_(
                [TermsOfServiceEngagement.Notified, TermsOfServiceEngagement.Agreed]
            )
        )
        .subquery()
    )
    users_to_notify = (
        request.db.query(User)
        .outerjoin(Email)
        .filter(Email.verified == True, Email.primary == True)  # noqa E711
        .filter(User.id.not_in(already_notified_subquery))
        .limit(request.registry.settings.get("terms.notification_batch_size"))
    )
    for user in users_to_notify:
        send_user_terms_of_service_updated(request, user)
        user_service.record_tos_engagement(
            user.id,
            request.registry.settings.get("terms.revision"),
            TermsOfServiceEngagement.Notified,
        )


@tasks.task(ignore_result=True, acks_late=True)
def compute_user_metrics(request):
    """
    Report metrics about the users in the database.
    """
    metrics = request.find_service(IMetricsService, context=None)

    # Total of users
    metrics.gauge(
        "warehouse.users.count",
        request.db.query(func.count(User.id)).scalar(),
    )

    # Total of active users
    metrics.gauge(
        "warehouse.users.count",
        request.db.query(func.count(User.id)).filter(User.is_active).scalar(),
        tags=["active:true"],
    )

    # Total active users with unverified emails
    metrics.gauge(
        "warehouse.users.count",
        request.db.query(func.count(User.id.distinct()))
        .outerjoin(Email)
        .filter(User.is_active)
        .filter((Email.verified == None) | (Email.verified == False))  # noqa E711
        .scalar(),
        tags=["active:true", "verified:false"],
    )

    # Total active users with unverified emails, and have project releases
    metrics.gauge(
        "warehouse.users.count",
        request.db.query(func.count(User.id.distinct()))
        .outerjoin(Email)
        .join(Release, Release.uploader_id == User.id)
        .filter(User.is_active)
        .filter((Email.verified == None) | (Email.verified == False))  # noqa E711
        .scalar(),
        tags=["active:true", "verified:false", "releases:true"],
    )

    # Total active users with unverified emails, and have project releases that
    # were uploaded within the past two years
    metrics.gauge(
        "warehouse.users.count",
        request.db.query(func.count(User.id.distinct()))
        .outerjoin(Email)
        .join(Release, Release.uploader_id == User.id)
        .filter(User.is_active)
        .filter((Email.verified == None) | (Email.verified == False))  # noqa E711
        .filter(Release.created > datetime.now(tz=timezone.utc) - timedelta(days=730))
        .scalar(),
        tags=["active:true", "verified:false", "releases:true", "window:2years"],
    )

    # Total active users with unverified primary emails, and have project
    # releases that were uploaded within the past two years
    metrics.gauge(
        "warehouse.users.count",
        request.db.query(func.count(User.id.distinct()))
        .outerjoin(Email)
        .join(Release, Release.uploader_id == User.id)
        .filter(User.is_active)
        .filter((Email.verified == None) | (Email.verified == False))  # noqa E711
        .filter(Email.primary)
        .filter(Release.created > datetime.now(tz=timezone.utc) - timedelta(days=730))
        .scalar(),
        tags=[
            "active:true",
            "verified:false",
            "releases:true",
            "window:2years",
            "primary:true",
        ],
    )


@tasks.task(ignore_result=True, acks_late=True)
def batch_update_email_domain_status(request: Request) -> None:
    """
    Update the email domain status for any checked over 30 days ago.

    30 days is roughly the time between a domain's expiration
    and when it enters a renewal grace period.
    Each TLD may express their own grace period, 30 days is an estimate
    of time before the registrar is likely to sell it.
    """
    stmt = (
        select(Email)
        .where(
            # TODO: After completely backfilled, remove the `or_` for None
            or_(
                Email.domain_last_checked.is_(None),
                Email.domain_last_checked < datetime.now(tz=UTC) - timedelta(days=30),
            )
        )
        .order_by(nullsfirst(Email.domain_last_checked.asc()))
        .limit(10_000)
    )
    # Run in batches to avoid too much memory usage, API rate limits
    stmt = stmt.execution_options(yield_per=1_000)

    for email in request.db.scalars(stmt):
        update_email_domain_status(email, request)
