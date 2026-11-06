# SPDX-License-Identifier: Apache-2.0

from zope.interface import Interface


class IApiKeyService(Interface):
    def create_api_key(user_id, name, scopes, expires):
        """
        Returns a tuple of the new raw key and its DB model. The raw key is
        not stored and cannot be recovered later.
        """

    def verify(raw_key):
        """
        Returns the DB model for an active key.

        Raises InvalidApiKeyError if the key is malformed, unknown or revoked,
        and ExpiredApiKeyError if it has expired.
        """

    def record_use(api_key_id):
        """
        Marks the key with the given ID as used now.
        """

    def revoke(api_key_id):
        """
        Revokes the key with the given ID, effective immediately.
        """
