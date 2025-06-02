# SPDX-License-Identifier: Apache-2.0

from warehouse.macaroons.errors import InvalidMacaroonError
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.services import database_macaroon_factory

__all__ = ["InvalidMacaroonError", "includeme"]


def includeme(config):
    config.register_service_factory(database_macaroon_factory, IMacaroonService)
