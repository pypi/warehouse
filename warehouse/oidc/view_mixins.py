# SPDX-License-Identifier: Apache-2.0

"""
Behavior shared by the views that manage Trusted Publishers, at the account,
organization, and project levels.
"""

from __future__ import annotations

import functools
import typing

from psycopg.errors import UniqueViolation
from pyramid.httpexceptions import HTTPSeeOther, HTTPTooManyRequests
from sqlalchemy import func, select

from warehouse.admin.flags import AdminFlagValue
from warehouse.oidc.interfaces import TooManyOIDCRegistrations
from warehouse.oidc.models import PendingOIDCPublisher
from warehouse.rate_limiting import IRateLimiter

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from pyramid.request import Request
    from wtforms import Form

    from warehouse.metrics import IMetricsService


OIDC_PUBLISHER_ADMIN_FLAGS: dict[str, AdminFlagValue] = {
    "GitHub": AdminFlagValue.DISALLOW_GITHUB_OIDC,
    "GitLab": AdminFlagValue.DISALLOW_GITLAB_OIDC,
    "Google": AdminFlagValue.DISALLOW_GOOGLE_OIDC,
    "ActiveState": AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC,
}


class OIDCPublisherViewMixin:
    """
    Rate limiting and admin-flag handling common to all Trusted Publisher
    management views.
    """

    request: Request

    @functools.cached_property
    def _ratelimiters(self):
        return {
            "user.oidc": self.request.find_service(
                IRateLimiter, name="user_oidc.publisher.register"
            ),
            "ip.oidc": self.request.find_service(
                IRateLimiter, name="ip_oidc.publisher.register"
            ),
        }

    def _hit_ratelimits(self):
        self._ratelimiters["user.oidc"].hit(self.request.user.id)
        self._ratelimiters["ip.oidc"].hit(self.request.remote_addr)

    def _check_ratelimits(self):
        if not self._ratelimiters["user.oidc"].test(self.request.user.id):
            raise TooManyOIDCRegistrations(
                resets_in=self._ratelimiters["user.oidc"].resets_in(
                    self.request.user.id
                )
            )

        if not self._ratelimiters["ip.oidc"].test(self.request.remote_addr):
            raise TooManyOIDCRegistrations(
                resets_in=self._ratelimiters["ip.oidc"].resets_in(
                    self.request.remote_addr
                )
            )

    def _disabled_publishers(self) -> dict[str, bool]:
        return {
            name: self.request.flags.disallow_oidc(flag)
            for name, flag in OIDC_PUBLISHER_ADMIN_FLAGS.items()
        }

    def _flash_oidc_disabled(self, publisher_name: str | None = None) -> None:
        """
        Flash the "temporarily disabled" error, either for Trusted Publishing as a
        whole or for a single publisher type.
        """
        mapping = {
            "docs_url": self.request.user_docs_url(
                "/about/security-and-internals/",
                anchor="temporarily-disabled-features",
            )
        }
        if publisher_name is None:
            message = self.request._(
                "Trusted publishing is temporarily disabled. "
                "See ${docs_url} for details.",
                mapping=mapping,
            )
        else:
            message = self.request._(
                f"{publisher_name}-based trusted publishing is temporarily "
                "disabled. See ${docs_url} for "
                "details.",
                mapping=mapping,
            )
        self.request.session.flash(message, queue="error")


class PendingOIDCPublisherViewMixin(OIDCPublisherViewMixin):
    """
    The "register a pending publisher" flow, shared by the account-level and
    organization-level publishing views.

    Subclasses customize the flow through the hooks below.
    """

    metrics: IMetricsService

    # Extra metric tags identifying the flow.
    _pending_metric_tags: typing.ClassVar[list[str]] = []

    @property
    def default_response(self) -> dict:
        raise NotImplementedError

    def _pending_count_scope(self):
        """SQL criterion scoping the per-user pending publisher limit."""
        raise NotImplementedError

    def _too_many_pending_message(self) -> str:
        raise NotImplementedError

    def _ratelimited_response(self, exc: TooManyOIDCRegistrations):
        raise NotImplementedError

    def _record_pending_publisher_added(self, additional: dict) -> None:
        raise NotImplementedError

    def _pending_publisher_added_message(self, pending_publisher) -> str:
        raise NotImplementedError

    def _too_many_requests(self, exc: TooManyOIDCRegistrations) -> HTTPTooManyRequests:
        return HTTPTooManyRequests(
            self.request._(
                "There have been too many attempted trusted publisher "
                "registrations. Try again later."
            ),
            retry_after=(
                exc.resets_in.total_seconds() if exc.resets_in is not None else None
            ),
        )

    def _add_pending_oidc_publisher(
        self,
        publisher_name: str,
        publisher_class: type[PendingOIDCPublisher],
        admin_flag: AdminFlagValue,
        form: Form,
        make_pending_publisher: Callable[[Request, typing.Any], PendingOIDCPublisher],
        make_existence_filters: Callable[[typing.Any], dict],
    ):
        if self.request.flags.disallow_oidc(admin_flag):
            self._flash_oidc_disabled(publisher_name)
            return self.default_response

        metric_tags = [f"publisher:{publisher_name}", *self._pending_metric_tags]
        self.metrics.increment(
            "warehouse.oidc.add_pending_publisher.attempt", tags=metric_tags
        )

        if not self.request.user.has_primary_verified_email:
            self.request.session.flash(
                self.request._(
                    "You must have a verified email in order to register a "
                    "pending trusted publisher. "
                    "See ${docs_url} for details.",
                    mapping={
                        "docs_url": self.request.user_docs_url(
                            "/your-account/managing-your-account/",
                            anchor="email-address-verification",
                        )
                    },
                ),
                queue="error",
            )
            return self.default_response

        # Separately from having permission to register pending OIDC publishers,
        # we limit each user to no more than 3 pending publishers at once within
        # a scope (personal, or per organization).
        pending_count = self.request.db.scalar(
            select(func.count()).where(
                self._pending_count_scope(),
                PendingOIDCPublisher.added_by_id == self.request.user.id,
            )
        )
        if pending_count >= 3:
            self.request.session.flash(self._too_many_pending_message(), queue="error")
            return self.default_response

        try:
            self._check_ratelimits()
        except TooManyOIDCRegistrations as exc:
            self.metrics.increment(
                "warehouse.oidc.add_pending_publisher.ratelimited", tags=metric_tags
            )
            return self._ratelimited_response(exc)

        self._hit_ratelimits()

        if not form.validate():
            self.request.session.flash(
                self.request._("The trusted publisher could not be registered"),
                queue="error",
            )
            return self.default_response

        publisher_already_exists = (
            self.request.db.query(publisher_class)
            .filter_by(**make_existence_filters(form))
            .first()
            is not None
        )

        if publisher_already_exists:
            self.request.session.flash(
                self.request._(
                    "This trusted publisher has already been registered. "
                    "Please contact PyPI's admins if this wasn't intentional."
                ),
                queue="error",
            )
            return self.default_response

        pending_publisher = make_pending_publisher(self.request, form)

        try:
            self.request.db.add(pending_publisher)
            self.request.db.flush()  # ast-grep-ignore: db-flush -- generate id
        except UniqueViolation:
            # The DB unique constraint covers (repo, owner, workflow,
            # environment) but not project_name, so this fires when another
            # pending publisher already targets the same external identity
            # under a different project name. Surface that conflict instead
            # of silently redirecting as if registration succeeded.
            #
            # The failed INSERT leaves the transaction in an aborted state, so
            # roll back before doing anything else with the session -- otherwise
            # rendering the response (or the end-of-request commit) blows up.
            self.request.db.rollback()
            self.request.session.flash(
                self.request._(
                    "A pending trusted publisher matching this configuration "
                    "has already been registered for a different project name. "
                    "Please contact PyPI's admins if this wasn't intentional."
                ),
                queue="error",
            )
            return self.default_response

        self._record_pending_publisher_added(
            {
                "project": pending_publisher.project_name,
                "publisher": pending_publisher.publisher_name,
                "id": str(pending_publisher.id),
                "specifier": str(pending_publisher),
                "url": pending_publisher.publisher_url(),
                "submitted_by": self.request.user.username,
            }
        )

        self.request.session.flash(
            self._pending_publisher_added_message(pending_publisher),
            queue="success",
        )

        self.metrics.increment(
            "warehouse.oidc.add_pending_publisher.ok", tags=metric_tags
        )

        return HTTPSeeOther(self.request.path)
