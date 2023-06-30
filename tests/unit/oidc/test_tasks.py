import pretend

from warehouse.oidc.tasks import compute_oidc_metrics

from ...common.db.oidc import GitHubPublisherFactory
from ...common.db.packaging import ProjectFactory


def test_compute_oidc_metrics(db_request, monkeypatch):
    # Projects with OIDC
    critical_project_oidc = ProjectFactory.create(
        name="critical_project_oidc", pypi_mandates_2fa=True
    )
    non_critical_project_oidc = ProjectFactory.create(
        name="non_critical_project_oidc",
    )

    # Projects without OIDC
    critical_project_no_oidc = ProjectFactory.create(
        name="critical_project_no_oidc", pypi_mandates_2fa=True
    )
    non_critical_project_no_oidc = ProjectFactory.create(
        name="non_critical_project_no_oidc",
    )

    # Create OIDC publishers. One OIDCPublisher can be shared by multiple
    # projects so 'oidc_publisher_1' represents that situation. Verify
    # that metrics don't double-count projects using multiple OIDC publishers.
    oidc_publisher_1 = GitHubPublisherFactory.create(
        projects=[critical_project_oidc, non_critical_project_oidc]
    )
    oidc_publisher_2 = GitHubPublisherFactory.create(projects=[critical_project_oidc])

    gauge = pretend.call_recorder(lambda metric, value: None)
    db_request.find_service = lambda *a, **kw: pretend.stub(gauge=gauge)

    compute_oidc_metrics(db_request)

    assert gauge.calls == [
        pretend.call("warehouse.oidc.total_projects_using_oidc_publishers", 2),
        pretend.call("warehouse.oidc.total_critical_projects_using_oidc_publishers", 1),
    ]
