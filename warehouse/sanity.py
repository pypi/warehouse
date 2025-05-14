# SPDX-License-Identifier: Apache-2.0

import urllib.parse

from pyramid.config import PHASE3_CONFIG
from pyramid.httpexceptions import HTTPBadRequest, HTTPException
from pyramid.interfaces import ITweens


def junk_encoding(request):
    # We're going to test our request a bit, before we pass it into the
    # handler. This will let us return a better error than a 500 if we
    # can't decode these.

    # Ref: https://github.com/Pylons/webob/issues/161
    # Ref: https://github.com/Pylons/webob/issues/115
    try:
        request.GET.get("", None)
    except UnicodeDecodeError:
        raise HTTPBadRequest("Invalid bytes in query string.")

    # Look for invalid bytes in a path.
    try:
        request.path_info
    except UnicodeDecodeError:
        raise HTTPBadRequest("Invalid bytes in URL.")


def invalid_forms(request):
    # People send invalid forms that we can't actually decode, so we'll want to return
    # a BadRequest here instead of a 500 error.
    if request.method == "POST":
        try:
            request.POST.get("", None)
        except ValueError:
            raise HTTPBadRequest("Invalid Form Data.")


def unicode_redirects(response):
    if response.location:
        try:
            response.location.encode("ascii")
        except UnicodeEncodeError:
            response.location = "/".join(
                [urllib.parse.quote_plus(x) for x in response.location.split("/")]
            )

    return response


def sanity_tween_factory_ingress(handler, registry):
    def sanity_tween_ingress(request):
        try:
            junk_encoding(request)
            invalid_forms(request)
        except HTTPException as exc:
            return exc

        return handler(request)

    return sanity_tween_ingress


def sanity_tween_factory_egress(handler, registry):
    def sanity_tween_egress(request):
        return unicode_redirects(handler(request))

    return sanity_tween_egress


def _add_tween(config):
    tweens = config.registry.queryUtility(ITweens)
    tweens.add_explicit(
        "warehouse.sanity.sanity_tween_factory_ingress", sanity_tween_factory_ingress
    )
    for tween_name, tween_factory in tweens.implicit():
        tweens.add_explicit(tween_name, tween_factory)
    tweens.add_explicit(
        "warehouse.sanity.sanity_tween_factory_egress", sanity_tween_factory_egress
    )


def includeme(config):
    # I'm doing bad things, I'm sorry. - dstufft
    config.action(
        ("tween", "warehouse.sanity.sanity_tween_factory", True),
        _add_tween,
        args=(config,),
        order=PHASE3_CONFIG,
    )
