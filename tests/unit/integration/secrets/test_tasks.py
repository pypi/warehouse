# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.integrations.secrets import tasks, utils


def test_analyze_disclosure_task(monkeypatch, someorigin):
    analyze_disclosure = pretend.call_recorder(lambda *a, **k: None)
    monkeypatch.setattr(utils, "analyze_disclosure", analyze_disclosure)

    request = pretend.stub()
    disclosure_record = pretend.stub()

    tasks.analyze_disclosure_task(
        request=request,
        disclosure_record=disclosure_record,
        origin=someorigin.to_dict(),
    )

    assert analyze_disclosure.calls == [
        pretend.call(
            request=request,
            disclosure_record=disclosure_record,
            origin=someorigin,
        )
    ]
