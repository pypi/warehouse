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

import pretend

from warehouse.integrations.vulnerabilities import tasks, utils


def test_analyze_disclosure_task(monkeypatch):
    analyze_vulnerability = pretend.call_recorder(lambda *a, **k: None)
    monkeypatch.setattr(utils, "analyze_vulnerability", analyze_vulnerability)

    metrics = pretend.stub()
    request = pretend.stub(find_service=lambda *a, **kw: metrics)
    vulnerability_report = pretend.stub()
    origin = pretend.stub()

    tasks.analyze_vulnerability_task(
        request=request,
        vulnerability_report=vulnerability_report,
        origin=origin,
    )

    assert analyze_vulnerability.calls == [
        pretend.call(
            request=request,
            vulnerability_report=vulnerability_report,
            origin=origin,
            metrics=metrics,
        )
    ]
