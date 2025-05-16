# SPDX-License-Identifier: Apache-2.0

from zope.interface import Interface


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


class RateLimiterException(Exception):
    def __init__(self, *args, resets_in, **kwargs):
        self.resets_in = resets_in

        return super().__init__(*args, **kwargs)
