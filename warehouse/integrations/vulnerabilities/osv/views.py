# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json

from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy.orm.exc import NoResultFound

from warehouse.integrations import vulnerabilities
from warehouse.integrations.vulnerabilities import osv, utils
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
        return Response(status=400)

    try:
        vulnerability_reports = request.json_body
    except json.decoder.JSONDecodeError:
        metrics.increment(
            "warehouse.vulnerabilties.error.payload.json_error", tags=["origin:osv"]
        )
        return Response(status=400)

    try:
        utils.analyze_vulnerabilities(
            request=request,
            vulnerability_reports=vulnerability_reports,
            origin="osv",
            metrics=metrics,
        )
    except vulnerabilities.InvalidVulnerabilityReportRequest:
        return Response(status=400)
    except NoResultFound:
        return Response(status=404)

    # 204 No Content: we acknowledge but we won't comment on the outcome.
    return Response(status=204)
