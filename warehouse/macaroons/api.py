from collections import defaultdict

from pyramid.httpexceptions import HTTPForbidden
from pyramid.view import view_config

from cornice import Service

import os
import binascii

from pyramid.httpexceptions import HTTPUnauthorized, HTTPBadRequest
from warehouse.macaroons.caveats import InvalidMacaroon
from warehouse.macaroons.interfaces import IMacaroonService

tokens = Service(name='token',
                path='test_token/{master_key}/{description}/{scope}/{version}/{expiration}',
                description='Create new api tokens for project uploads.')


@tokens.post(validators=[valid_master,valid_scope])
def create_token(request):
    macaroon_service = request.find_service(IMacaroonService, context=None)
    token = request.validated['api_key']
    return {'api_key': token}

def valid_master(request, **kargs):
    macaroon_service = request.find_service(IMacaroonService, context=None)
    try:
        macaroon_service.verify(request.master_key) #add params for all projects TODO
    except InvalidMacaroon:
        raise HTTPUnauthorized()

def valid_scope(request, **kargs):
    macaroon_service = request.find_service(IMacaroonService, context=None)
    try:
        user = macaroon_service.find_userid(request.master_key) #to determine the user of the original token
        scope = {"version": 2, "permissions": scope}
        serialized_macaroon, macaroon = macaroon_service.create_macaroon(...) # TODO
    except ValueError or InvalidMacaroon:
        raise HTTPBadRequest()
    request.validated['api_key'] = serialized_macaroon