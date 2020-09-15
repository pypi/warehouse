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

from warehouse.integrations.github import tasks, utils


def test_analyze_disclosure_task(monkeypatch):
    analyze_disclosure = pretend.call_recorder(lambda *a, **k: None)
    monkeypatch.setattr(utils, "analyze_disclosure", analyze_disclosure)

    task = pretend.stub()
    request = pretend.stub()
    disclosure_record = pretend.stub()
    origin = pretend.stub()

    tasks.analyze_disclosure_task(
        task=task,
        request=request,
        disclosure_record=disclosure_record,
        origin=origin,
    )

    assert analyze_disclosure.calls == [
        pretend.call(
            request=request,
            disclosure_record=disclosure_record,
            origin=origin,
        )
    ]
