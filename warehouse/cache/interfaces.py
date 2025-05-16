# SPDX-License-Identifier: Apache-2.0

from zope.interface import Interface


class IQueryResultsCache(Interface):
    """
    A cache for expensive/slow database query results.

    Example usage:

    >>> some_expensive_query = request.db.query(...)
    >>> cache_service = request.find_service(IQueryResultsCache)
    >>> cache_service.set("some_key_name", some_expensive_query)

    # Later, retrieve the cached results:
    >>> results = cache_service.get("some_key_name")
    """

    def create_service(context, request):
        """Create the service, bootstrap any configuration needed."""

    def get(key: str):
        """Get a cached result by key."""

    def set(key: str, value):
        """Set a cached result by key."""
        # TODO: do we need a set-with-expiration, a la `setex`?
