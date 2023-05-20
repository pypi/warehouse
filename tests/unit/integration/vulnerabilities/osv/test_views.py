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

import collections
import json

import pretend

from warehouse.integrations.vulnerabilities import osv
from warehouse.integrations.vulnerabilities.osv import views


class TestReportVulnerabilities:
    def test_report_vulnerabilities(self, pyramid_request, monkeypatch):
        pyramid_request.headers = {
            "VULN-PUBLIC-KEY-IDENTIFIER": "vuln_pub_key_id",
            "VULN-PUBLIC-KEY-SIGNATURE": "vuln_pub_key_sig",
        }
        metrics = pretend.stub()

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

        http = pyramid_request.http = pretend.stub()

        verify = pretend.call_recorder(lambda **k: True)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(osv, "VulnerabilityReportVerifier", verifier_cls)

        delay = pretend.call_recorder(lambda **k: None)
        task = pretend.call_recorder(lambda a: pretend.stub(delay=delay))
        pyramid_request.task = task

        response = views.report_vulnerabilities(pyramid_request)

        assert response.status_code == 204
        assert verifier_cls.calls == [pretend.call(session=http, metrics=metrics)]
        assert verify.calls == [
            pretend.call(
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
        ]
        assert task.calls == [pretend.call(views.analyze_vulnerability_task)]
        assert delay.calls == [
            pretend.call(
                vulnerability_report={
                    "project": "vuln_project",
                    "versions": ["v1", "v2"],
                    "id": "vuln_id",
                    "link": "vulns.com/vuln_id",
                    "aliases": ["vuln_alias"],
                },
                origin="osv",
            )
        ]

    def test_report_vulnerabilities_verify_fail(self, monkeypatch, pyramid_request):
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

        pyramid_request.http = pretend.stub()

        verify = pretend.call_recorder(lambda **k: False)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(osv, "VulnerabilityReportVerifier", verifier_cls)

        response = views.report_vulnerabilities(pyramid_request)

        assert response.status_int == 400

    def test_report_vulnerabilities_verify_invalid_json(self, monkeypatch):
        verify = pretend.call_recorder(lambda **k: True)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(osv, "VulnerabilityReportVerifier", verifier_cls)

        metrics = collections.Counter()

        def metrics_increment(key, tags):
            metrics.update([(key, tuple(tags))])

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
                return pretend.stub(increment=metrics_increment)

            response = pretend.stub(status_int=200)
            http = pretend.stub()

        request = Request()
        response = views.report_vulnerabilities(request)

        assert response.status_int == 400
        assert metrics == {
            (
                "warehouse.vulnerabilties.error.payload.json_error",
                ("origin:osv",),
            ): 1,
        }

    def test_report_vulnerabilities_verify_invalid_vuln(
        self, monkeypatch, pyramid_request
    ):
        pyramid_request.headers = {
            "VULN-PUBLIC-KEY-IDENTIFIER": "vuln_pub_key_id",
            "VULN-PUBLIC-KEY-SIGNATURE": "vuln_pub_key_sig",
        }

        pyramid_request.body = "{}"  # not a list
        pyramid_request.json_body = {}

        pyramid_request.http = pretend.stub()

        verify = pretend.call_recorder(lambda **k: True)
        verifier = pretend.stub(verify=verify)
        verifier_cls = pretend.call_recorder(lambda **k: verifier)
        monkeypatch.setattr(osv, "VulnerabilityReportVerifier", verifier_cls)

        response = views.report_vulnerabilities(pyramid_request)

        assert response.status_int == 400
