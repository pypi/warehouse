# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from zope.interface import Attribute, Interface


class IGatePolicy(Interface):
    """
    Decides whether a release needs a hold of one kind, and how long that hold
    may stay pending.

    A policy does not resolve its own gates; whatever does the work calls
    `IGateService.resolve`. Register one with `config.register_gate_policy`.
    """

    kind = Attribute(
        "Short stable identifier for this hold, written to `ReleaseGate.kind`"
    )
    timeout = Attribute(
        "`timedelta` after which a still-pending gate is swept, or None to "
        "wait indefinitely"
    )
    timeout_status = Attribute("The `GateStatus` the sweep applies on timeout")

    def applies(release, request):
        """
        Return True if `release` should carry this hold.

        Called on every upload, so this must be cheap and must not mutate
        anything.
        """


class IGateService(Interface):
    """
    Opens, resolves and reports on release gates, and keeps the denormalized
    `Release.gated` flag in step with them.

    `Release.gated` is what the hot read paths filter on, so it must only ever
    be written through this service.
    """

    def register_policy(policy):
        """Add an `IGatePolicy`. Raises `ValueError` on a duplicate kind."""

    def policy_for(kind):
        """Return the registered policy for `kind`, or None if there is none."""

    def policies():
        """Return the registered policies, in registration order."""

    def open_gates(release, request):
        """
        Open a pending gate for every registered policy that `applies` to
        `release`, and withhold the release if any now block.

        Idempotent per (release, kind): a kind that already has a gate is reset
        to pending rather than duplicated, so a new file arriving in an
        already-cleared release is re-held pending a fresh decision.

        Returns the list of `ReleaseGate` rows that are now pending.
        """

    def resolve(release, kind, status, *, note=None, resolved_by=None, details=None):
        """
        Move one gate out of (or back into) a blocking state and recompute
        whether the release is still withheld.

        Returns the updated `ReleaseGate`, or None if no such gate exists.
        """

    def blocking_gates(release):
        """Return the gates currently withholding `release`."""

    def is_gated(release):
        """
        Return whether `release` is withheld, computed from its gates rather
        than read off the denormalized flag.
        """
