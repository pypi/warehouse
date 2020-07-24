import json

from pyramid.response import Response
from pyramid.view import view_config

from warehouse.integrations.github import utils
from warehouse.metrics import IMetricsService


@view_config(
    require_methods=["POST"],
    require_csrf=False,
    renderer="json",
    route_name="accounts.github-disclose-token",
    # If those headers are missing, response will be a 404
    headers=["GITHUB-PUBLIC-KEY-IDENTIFIER", "GITHUB-PUBLIC-KEY-SIGNATURE"],
    has_translations=False,
)
def github_disclose_token(request):
    # GitHub calls this API view when they have identified a string matching
    # the regular expressions we provided them.
    # Our job is to validate we're talking to github, check if the string contains
    # valid credentials and, if they do, invalidate them and warn the owner

    # The documentation for this process is at
    # https://developer.github.com/partnerships/token-scanning/

    body = request.body

    # Thanks to the predicates, we know the headers we need are defined.
    key_id = request.headers.get("GITHUB-PUBLIC-KEY-IDENTIFIER")
    signature = request.headers.get("GITHUB-PUBLIC-KEY-SIGNATURE")
    metrics = request.find_service(IMetricsService, context=None)

    verifier = utils.GitHubTokenScanningPayloadVerifier(
        session=request.http,
        metrics=metrics,
        api_token=request.registry.settings["github.token"],
    )

    if not verifier.verify(payload=body, key_id=key_id, signature=signature):
        return Response(status=400)

    try:
        disclosures = request.json_body
    except json.decoder.JSONDecodeError:
        metrics.increment("warehouse.token_leak.github.error.payload.json_error")
        return Response(status=400)

    analyzer = utils.TokenLeakAnalyzer(request=request)

    try:
        analyzer.analyze_disclosures(disclosure_records=disclosures, origin="github")
    except utils.InvalidTokenLeakRequest:
        return Response(status=400)

    # 204 No Content: we acknowledge but we won't comment on the outcome.#
    return Response(status=204)
