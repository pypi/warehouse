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

import pytest

from warehouse.integrations.vulnerabilities import (
    InvalidVulnerabilityReportRequest,
    VulnerabilityReportRequest,
)


@pytest.mark.parametrize(
    "record, error, reason",
    [
        (None, "Record is not a dict but: None", "format"),
        (
            {},
            "Record is missing attribute(s): aliases, id, link, project, versions",
            "format",
        ),
    ],
)
def test_vulnerability_report_request_from_api_request_error(record, error, reason):

    with pytest.raises(InvalidVulnerabilityReportRequest) as exc:
        VulnerabilityReportRequest.from_api_request(record)

    assert str(exc.value) == error
    assert exc.value.reason == reason


def test_vulnerability_report_request_from_api_request():
    request = VulnerabilityReportRequest.from_api_request(
        request={
            "project": "vuln_project",
            "versions": ["v1", "v2"],
            "id": "vuln_id",
            "link": "vulns.com/vuln_id",
            "aliases": ["vuln_alias"],
        }
    )

    assert request.project == "vuln_project"
    assert request.versions == ["v1", "v2"]
    assert request.vulnerability_id == "vuln_id"
    assert request.advisory_link == "vulns.com/vuln_id"
    assert request.aliases == ["vuln_alias"]


def test_invalid_vulnerability_report():
    exc = InvalidVulnerabilityReportRequest("error string", "reason")

    assert str(exc) == "error string"
    assert exc.reason == "reason"
