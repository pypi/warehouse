from warehouse import tasks
from warehouse.integrations.github.utils import analyze_disclosure


@tasks.task(ignore_result=True, acks_late=True)
def analyze_disclosure_task(task, request, disclosure_record, origin):
    analyze_disclosure(
        request=request, disclosure_record=disclosure_record, origin=origin,
    )
