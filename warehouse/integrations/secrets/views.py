# SPDX-License-Identifier: Apache-2.0

import json

from pyramid.httpexceptions import HTTPBadRequest, HTTPNoContent, HTTPNotFound
from pyramid.view import view_config

from warehouse.integrations.secrets import config, utils
from warehouse.metrics import IMetricsService


def _detect_origin(request):
    for origin in config.origins:
        if all([k in request.headers for k in origin.headers]):
            return origin


@view_config(
    require_methods=["POST"],
    require_csrf=False,
    renderer="json",
    route_name="integrations.secrets.disclose-token",
    has_translations=False,
)
@view_config(
    require_methods=["POST"],
    require_csrf=False,
    renderer="json",
    route_name="integrations.github.disclose-token",  # For backwards compatibility
    has_translations=False,
)
def disclose_token(request):
    metrics = request.find_service(IMetricsService, context=None)

    # If integrator headers are missing, response will be a 404
    if not (origin := _detect_origin(request)):
        metrics.increment("warehouse.token_leak.invalid_origin")
        return HTTPNotFound()

    # Disclosers calls this API view when they have identified a string matching
    # the regular expressions we provided them.
    # Our job is to validate we're talking to the origin, check if the string
    # contains valid credentials and, if they do, invalidate them and warn the
    # owner

    # The documentation for this process is at
    # https://developer.github.com/partnerships/token-scanning/
    key_id = request.headers.get(origin.key_id_header)
    signature = request.headers.get(origin.signature_header)

    verifier = utils.GenericTokenScanningPayloadVerifier(
        session=request.http,
        metrics=metrics,
        origin=origin,
        api_url=origin.verification_url,
        api_token=request.registry.settings.get(origin.api_token),
    )

    if not verifier.verify(payload=request.body, key_id=key_id, signature=signature):
        metrics.increment(
            f"warehouse.token_leak.{origin.metric_name}.error.payload.verify_error"
        )
        return HTTPBadRequest()

    try:
        disclosures = request.json_body
    except json.decoder.JSONDecodeError:
        metrics.increment(
            f"warehouse.token_leak.{origin.metric_name}.error.payload.json_error"
        )
        return HTTPBadRequest()

    try:
        utils.analyze_disclosures(
            request=request,
            disclosure_records=disclosures,
            origin=origin,
            metrics=metrics,
        )
    except utils.InvalidTokenLeakRequestError:
        return HTTPBadRequest()

    # 204 No Content: we acknowledge but we won't comment on the outcome.
    return HTTPNoContent()
