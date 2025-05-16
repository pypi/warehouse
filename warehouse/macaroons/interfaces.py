# SPDX-License-Identifier: Apache-2.0

from zope.interface import Interface


class IMacaroonService(Interface):
    def find_from_raw(raw_macaroon):
        """
        Returns a macaroon model from the DB from a raw macaroon, or raises
        InvalidMacaroon if not found or for malformed macaroons.
        """

    def find_macaroon(macaroon_id):
        """
        Returns a macaroon model from the DB by its identifier.
        Returns None if no macaroon has the given ID.
        """

    def find_userid(raw_macaroon):
        """
        Returns the id of the user associated with the given raw (serialized)
        macaroon.
        """

    def verify(raw_macaroon, request, context, permission):
        """
        Returns True if the given raw (serialized) macaroon is
        valid for the request, context, and requested permission.

        Raises InvalidMacaroonError if the macaroon is not valid.
        """

    def create_macaroon(
        location,
        description,
        scopes,
        *,
        user_id=None,
        oidc_publisher_id=None,
        additional=None
    ):
        """
        Returns a tuple of a new raw (serialized) macaroon and its DB model.
        The description provided is not embedded into the macaroon, only stored
        in the DB model.

        An associated identity (either a user or macaroon, by ID) must be specified.
        """

    def delete_macaroon(macaroon_id):
        """
        Deletes a macaroon from the DB by its identifier.
        """

    def get_macaroon_by_description(user_id, description):
        """
        Returns a macaroon model from the DB with the given description,
        if one exists for the given user.

        Returns None if the user doesn't have a macaroon with this description.
        """
