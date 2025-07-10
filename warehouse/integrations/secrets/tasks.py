# SPDX-License-Identifier: Apache-2.0

from warehouse import tasks
from warehouse.integrations.secrets import utils


@tasks.task(ignore_result=True, acks_late=True)
def analyze_disclosure_task(request, disclosure_record, origin):
    origin = utils.DisclosureOrigin.from_dict(origin)
    utils.analyze_disclosure(
        request=request,
        disclosure_record=disclosure_record,
        origin=origin,
    )
