@view_config(
    require_methods=["POST"],
    require_csrf=False,
    renderer="json",
    route_name="accounts.github-disclose-token",
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

    verifier = request.find_service(
        IGitHubTokenScanningPayloadVerifyService, context=None
    )

    if not verifier.verify(payload=body, key_id=key_id, signature=signature):
        request.response.status_int = 403
        return {"error": "invalid signature"}

    try:
        disclosures = request.json_body
    except json.decoder.JSONDecodeError:
        request.response.status_int = 400
        return {"error": "body is not valid json"}

    analyzer = TokenLeakAnalyzer(request=request)

    try:
        analyzer.analyze_disclosures(disclosure_records=disclosures, origin="github")
    except InvalidTokenLeakRequest:
        request.response.status_int = 400
        return {"error": "cannot read disclosures from payload"}

    # 204 No Content: we acknowledge but we won't comment on the outcome.#
    return Response(status=204)
