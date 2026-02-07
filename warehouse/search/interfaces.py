# SPDX-License-Identifier: Apache-2.0

from zope.interface import Interface


class ISearchService(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for.
        """

    def reindex(config, projects_to_update):
        """
        Reindexes any projects provided
        """

    def unindex(config, projects_to_delete):
        """
        Unindexes any projects provided
        """
