# SPDX-License-Identifier: Apache-2.0

import json

from pyramid.httpexceptions import HTTPBadRequest, HTTPNoContent
from pyramid.view import view_config

from warehouse.integrations.vulnerabilities import osv
from warehouse.integrations.vulnerabilities.tasks import analyze_vulnerability_task
from warehouse.metrics import IMetricsService


@view_config(
    require_methods=["POST"],
    require_csrf=False,
    renderer="json",
    route_name="integrations.vulnerabilities.osv.report",
    # If those headers are missing, response will be a 404
    require_headers=["VULN-PUBLIC-KEY-IDENTIFIER", "VULN-PUBLIC-KEY-SIGNATURE"],
    has_translations=False,
)
def report_vulnerabilities(request):
    # Vulnerability sources call this API view when they have identified a
    # vulnerability that affects a project release.

    body = request.body

    # Thanks to the predicates, we know the headers we need are defined.
    key_id = request.headers.get("VULN-PUBLIC-KEY-IDENTIFIER")
    signature = request.headers.get("VULN-PUBLIC-KEY-SIGNATURE")
    metrics = request.find_service(IMetricsService, context=None)

    verifier = osv.VulnerabilityReportVerifier(
        session=request.http,
        metrics=metrics,
    )

    if not verifier.verify(payload=body, key_id=key_id, signature=signature):
        return HTTPBadRequest()

    # Body must be valid JSON
    try:
        vulnerability_reports = request.json_body
    except json.decoder.JSONDecodeError:
        metrics.increment(
            "warehouse.vulnerabilities.error.payload.json_error", tags=["origin:osv"]
        )
        return HTTPBadRequest(body="Invalid JSON")

    # Body must be a list
    if not isinstance(vulnerability_reports, list):
        metrics.increment("warehouse.vulnerabilities.error.format", tags=["origin:osv"])
        return HTTPBadRequest(body="Invalid format: payload is not a list")

    # Create a task to analyze each report
    for vulnerability_report in vulnerability_reports:
        request.task(analyze_vulnerability_task).delay(
            vulnerability_report=vulnerability_report,
            origin="osv",
        )

    # 204 No Content: we acknowledge but we won't comment on the outcome.
    return HTTPNoContent()
