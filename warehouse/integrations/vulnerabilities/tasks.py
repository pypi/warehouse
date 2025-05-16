# SPDX-License-Identifier: Apache-2.0

from sqlalchemy import func, orm
from sqlalchemy.exc import NoResultFound

from warehouse import tasks
from warehouse.integrations import vulnerabilities
from warehouse.integrations.vulnerabilities.models import VulnerabilityRecord
from warehouse.metrics import IMetricsService
from warehouse.packaging.models import Project, Release


@tasks.task(ignore_result=True, acks_late=True)
def analyze_vulnerability_task(request, vulnerability_report, origin):
    metrics = request.find_service(IMetricsService, context=None)

    metrics.increment("warehouse.vulnerabilities.received", tags=[f"origin:{origin}"])
    with metrics.timed("warehouse.vulnerabilities.analysis", tags=[f"origin:{origin}"]):
        try:
            report = vulnerabilities.VulnerabilityReportRequest.from_api_request(
                request=vulnerability_report
            )
        except vulnerabilities.InvalidVulnerabilityReportError as exc:
            metrics.increment(
                f"warehouse.vulnerabilities.error.{exc.reason}",
                tags=[f"origin:{origin}"],
            )
            return

        metrics.increment("warehouse.vulnerabilities.valid", tags=[f"origin:{origin}"])

        # See if we have an existing VulnerabilityRecord for this report
        vulnerability_record = (
            request.db.query(VulnerabilityRecord)
            .filter(VulnerabilityRecord.id == report.vulnerability_id)
            .filter(VulnerabilityRecord.source == origin)
            .options(orm.joinedload(VulnerabilityRecord.releases))
            .one_or_none()
        )

        # No versions indicates the vulnerability is no longer considered valid
        if not report.versions:
            # If we already have a record, delete it
            if vulnerability_record:
                request.db.delete(vulnerability_record)
        else:
            # If we don't have a vulnerability record, create it
            if not vulnerability_record:
                vulnerability_record = VulnerabilityRecord(
                    id=report.vulnerability_id,
                    source=origin,
                    link=report.advisory_link,
                    aliases=report.aliases,
                    details=report.details,
                    summary=report.summary,
                    fixed_in=report.fixed_in,
                    withdrawn=report.withdrawn,
                )
                request.db.add(vulnerability_record)

            # Otherwise, update it
            else:
                vulnerability_record.link = report.advisory_link
                vulnerability_record.aliases = report.aliases
                vulnerability_record.details = report.details
                vulnerability_record.summary = report.summary
                vulnerability_record.fixed_in = report.fixed_in
                vulnerability_record.withdrawn = report.withdrawn

            # Update the relationships between versions
            try:
                project = (
                    request.db.query(Project)
                    .filter(
                        Project.normalized_name
                        == func.normalize_pep426_name(report.project)
                    )
                    .one()
                )

            except NoResultFound:
                metrics.increment(
                    "warehouse.vulnerabilities.error.project_not_found",
                    tags=[f"origin:{origin}"],
                )
                return

            found_releases = False  # by now, we don't have any release found

            for version in report.versions:
                try:
                    release = (
                        request.db.query(Release)
                        .filter(Release.project_id == project.id)
                        .filter(Release.version == version)
                        .one()
                    )
                    found_releases = True  # at least one release found
                except NoResultFound:
                    metrics.increment(
                        "warehouse.vulnerabilities.error.release_not_found",
                        tags=[f"origin:{origin}"],
                    )
                    continue  # skip that release

                if release not in vulnerability_record.releases:
                    vulnerability_record.releases.append(release)

            if not found_releases:
                # no releases found, log this
                metrics.increment(
                    "warehouse.vulnerabilities.error.no_releases_found",
                    tags=[f"origin:{origin}"],
                )

            # Unassociate any releases that no longer apply.
            for release in list(vulnerability_record.releases):
                if release.version not in report.versions:
                    vulnerability_record.releases.remove(release)

    metrics.increment("warehouse.vulnerabilities.processed", tags=[f"origin:{origin}"])
