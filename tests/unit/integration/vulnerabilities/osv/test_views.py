# SPDX-License-Identifier: Apache-2.0

import json
import types

from warehouse.integrations.vulnerabilities import osv
from warehouse.integrations.vulnerabilities.osv import views


class TestReportVulnerabilities:
    def test_report_vulnerabilities(self, pyramid_request, metrics, mocker):
        pyramid_request.headers = {
            "VULN-PUBLIC-KEY-IDENTIFIER": "vuln_pub_key_id",
            "VULN-PUBLIC-KEY-SIGNATURE": "vuln_pub_key_sig",
        }

        pyramid_request.body = """[{
  "project": "vuln_project",
  "versions": [
    "v1",
    "v2"
  ],
  "id": "vuln_id",
  "link": "vulns.com/vuln_id",
  "aliases": [
    "vuln_alias"
  ]
}]"""
        pyramid_request.json_body = [
            {
                "project": "vuln_project",
                "versions": ["v1", "v2"],
                "id": "vuln_id",
                "link": "vulns.com/vuln_id",
                "aliases": ["vuln_alias"],
            }
        ]
        pyramid_request.find_service = lambda *a, **k: metrics

        http = pyramid_request.http = mocker.sentinel.http

        verifier_cls = mocker.patch.object(
            osv, "VulnerabilityReportVerifier", autospec=True
        )
        verifier_cls.return_value.verify.return_value = True

        delay = mocker.Mock()
        task = pyramid_request.task = mocker.Mock(return_value=mocker.Mock(delay=delay))

        response = views.report_vulnerabilities(pyramid_request)

        assert response.status_code == 204
        verifier_cls.assert_called_once_with(session=http, metrics=metrics)
        verifier_cls.return_value.verify.assert_called_once_with(
            payload="""[{
  "project": "vuln_project",
  "versions": [
    "v1",
    "v2"
  ],
  "id": "vuln_id",
  "link": "vulns.com/vuln_id",
  "aliases": [
    "vuln_alias"
  ]
}]""",
            key_id="vuln_pub_key_id",
            signature="vuln_pub_key_sig",
        )
        task.assert_called_once_with(views.analyze_vulnerability_task)
        delay.assert_called_once_with(
            vulnerability_report={
                "project": "vuln_project",
                "versions": ["v1", "v2"],
                "id": "vuln_id",
                "link": "vulns.com/vuln_id",
                "aliases": ["vuln_alias"],
            },
            origin="osv",
        )

    def test_report_vulnerabilities_verify_fail(self, mocker, pyramid_request):
        pyramid_request.headers = {
            "VULN-PUBLIC-KEY-IDENTIFIER": "vuln_pub_key_id",
            "VULN-PUBLIC-KEY-SIGNATURE": "vuln_pub_key_sig",
        }

        pyramid_request.body = """[{
  "project": "vuln_project",
  "versions": [
    "v1",
    "v2"
  ],
  "id": "vuln_id",
  "link": "vulns.com/vuln_id",
  "aliases": [
    "vuln_alias"
  ]
}]"""

        pyramid_request.http = mocker.sentinel.http

        verifier_cls = mocker.patch.object(
            osv, "VulnerabilityReportVerifier", autospec=True
        )
        verifier_cls.return_value.verify.return_value = False

        response = views.report_vulnerabilities(pyramid_request)

        assert response.status_int == 400

    def test_report_vulnerabilities_verify_invalid_json(self, metrics, mocker):
        verifier_cls = mocker.patch.object(
            osv, "VulnerabilityReportVerifier", autospec=True
        )
        verifier_cls.return_value.verify.return_value = True

        # We need to raise on a property access, can't do that with a stub.
        class Request:
            headers = {
                "VULN-PUBLIC-KEY-IDENTIFIER": "vuln_pub_key_id",
                "VULN-PUBLIC-KEY-SIGNATURE": "vuln_pub_key_sig",
            }
            body = "["

            @property
            def json_body(self):
                return json.loads(self.body)

            def find_service(self, *a, **k):
                return metrics

            response = types.SimpleNamespace(status_int=200)
            http = mocker.sentinel.http

        request = Request()
        response = views.report_vulnerabilities(request)

        assert response.status_int == 400
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.vulnerabilities.error.payload.json_error",
                tags=["origin:osv"],
            )
        ]

    def test_report_vulnerabilities_verify_invalid_vuln(self, mocker, pyramid_request):
        pyramid_request.headers = {
            "VULN-PUBLIC-KEY-IDENTIFIER": "vuln_pub_key_id",
            "VULN-PUBLIC-KEY-SIGNATURE": "vuln_pub_key_sig",
        }

        pyramid_request.body = "{}"  # not a list
        pyramid_request.json_body = {}

        pyramid_request.http = mocker.sentinel.http

        verifier_cls = mocker.patch.object(
            osv, "VulnerabilityReportVerifier", autospec=True
        )
        verifier_cls.return_value.verify.return_value = True

        response = views.report_vulnerabilities(pyramid_request)

        assert response.status_int == 400
