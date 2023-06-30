from warehouse import tasks
from warehouse.metrics import IMetricsService
from warehouse.packaging.models import Project


@tasks.task(ignore_result=True, acks_late=True)
def compute_oidc_metrics(request):
    metrics = request.find_service(IMetricsService, context=None)

    projects_using_oidc = (
        request.db.query(Project).distinct().join(Project.oidc_publishers)
    )

    # Metric for count of all projects using OIDC
    metrics.gauge(
        "warehouse.oidc.total_projects_using_oidc_publishers",
        projects_using_oidc.count(),
    )

    # Metric for count of critical projects using OIDC
    metrics.gauge(
        "warehouse.oidc.total_critical_projects_using_oidc_publishers",
        projects_using_oidc.where(Project.pypi_mandates_2fa.is_(True)).count(),
    )
