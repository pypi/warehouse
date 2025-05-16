# SPDX-License-Identifier: Apache-2.0

from zope.interface import Interface


class ISponsorLogoStorage(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for, passing a name for settings.
        """

    def store(path, file_path, content_type=None, *, meta=None):
        """
        Save the file located at file_path to the file storage at the location
        specified by path. An additional meta keyword argument may contain
        extra information that an implementation may or may not store.

        Returns public URL for the stored file.
        """
