# SPDX-License-Identifier: Apache-2.0

from warehouse.integrations.secrets import tasks, utils


def test_analyze_disclosure_task(mocker, someorigin):
    analyze_disclosure = mocker.patch.object(utils, "analyze_disclosure", autospec=True)

    request = mocker.sentinel.request
    disclosure_record = mocker.sentinel.disclosure_record

    tasks.analyze_disclosure_task(
        request=request,
        disclosure_record=disclosure_record,
        origin=someorigin.to_dict(),
    )

    analyze_disclosure.assert_called_once_with(
        request=request,
        disclosure_record=disclosure_record,
        origin=someorigin,
    )
