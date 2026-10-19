# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass

from zope.interface import Interface


@dataclass(frozen=True)
class WindowStats:
    """A snapshot of one rate-limit policy's state for a given identifier."""

    amount: int
    window_seconds: int
    remaining: int
    resets_in_seconds: int


class IRateLimiter(Interface):
    def test(*identifiers):
        """
        Checks if the rate limit identified by the identifiers has been
        reached, returning a boolean to indicate whether or not to allow the
        action.
        """

    def hit(*identifiers):
        """
        Registers a hit for the rate limit identified by the identifiers. This
        will return a boolean to indicate whether or not to allow the action
        for which a hit has been registered.
        """

    def resets_in(*identifiers):
        """
        Returns a timedelta indicating how long until the rate limit identified
        by identifiers will reset.
        """

    def clear(*identifiers):
        """
        Clears the rate limiter identified by the identifiers.
        """

    def get_window_stats(*identifiers):
        """
        Returns a list of WindowStats — one per configured policy — describing
        the current state for these identifiers. Returns an empty list if the
        backing storage is unavailable.
        """

    def override(limit_string):
        """
        Return a limiter using ``limit_string`` instead of the default.
        """


class RateLimiterException(Exception):  # noqa: N818
    def __init__(self, *args, resets_in, **kwargs):
        self.resets_in = resets_in

        super().__init__(*args, **kwargs)
