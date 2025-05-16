# SPDX-License-Identifier: Apache-2.0

from zope.interface import Interface


class IOriginCache(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for.
        """

    def cache(
        keys,
        request,
        response,
        *,
        seconds=None,
        stale_while_revalidate=None,
        stale_if_error=None
    ):
        """
        A hook that will be called after the request has been processed, used
        to associate the request and/or the response with the origin cache
        keys.

        The seconds argument is optional, and if provided should be used to
        override the number of seconds the origin cache will store the object.

        The stale_while_revalidate and stale_if_error arguments are optional,
        and if provided will be the number of seconds that a stale response
        will be valid for.
        """

    def purge(keys):
        """
        Purge and responses associated with the specific keys.
        """
