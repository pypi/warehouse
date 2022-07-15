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

from pyramid.httpexceptions import HTTPBadRequest
from sqlalchemy import func, orm
from sqlalchemy.orm.exc import NoResultFound

from warehouse.integrations import vulnerabilities
from warehouse.integrations.vulnerabilities.models import VulnerabilityRecord
from warehouse.packaging.models import Project, Release


def _get_project(request, vuln_report: vulnerabilities.VulnerabilityReportRequest):
    return (
        request.db.query(Project)
        .filter(
            Project.normalized_name == func.normalize_pep426_name(vuln_report.project)
        )
        .one()
    )


def _get_release(request, project: Project, version):
    return (
        request.db.query(Release)
        .filter(Release.project_id == project.id)
        .filter(Release.version == version)
        .one()
    )


def _get_vuln_record(
    request, vuln_report: vulnerabilities.VulnerabilityReportRequest, origin
):
    return (
        request.db.query(VulnerabilityRecord)
        .filter(VulnerabilityRecord.id == vuln_report.vulnerability_id)
        .filter(VulnerabilityRecord.source == origin)
        .options(orm.joinedload(VulnerabilityRecord.releases))
        .one()
    )


def _delete_vuln_record(request, vuln_record: VulnerabilityRecord):
    request.db.delete(vuln_record)


def _add_vuln_record(request, vuln_record: VulnerabilityRecord):
    request.db.add(vuln_record)


def _analyze_vulnerability(request, vulnerability_report, origin, metrics):
    try:
        report = vulnerabilities.VulnerabilityReportRequest.from_api_request(
            request=vulnerability_report
        )
    except vulnerabilities.InvalidVulnerabilityReportError as exc:
        metrics.increment(
            f"warehouse.vulnerabilities.error.{exc.reason}", tags=[f"origin:{origin}"]
        )
        raise

    metrics.increment("warehouse.vulnerabilities.valid", tags=[f"origin:{origin}"])

    try:
        vulnerability_record = _get_vuln_record(request, report, origin)

        if not report.versions:
            # No versions indicates the vulnerability is no longer considered
            # valid, so delete it.
            _delete_vuln_record(request, vulnerability_record)
            return

    except NoResultFound:
        if not report.versions:
            return

        vulnerability_record = VulnerabilityRecord(
            id=report.vulnerability_id,
            source=origin,
            link=report.advisory_link,
            aliases=report.aliases,
            details=report.details,
            summary=report.summary,
            fixed_in=report.fixed_in,
        )
        _add_vuln_record(request, vulnerability_record)

    try:
        project = _get_project(request, report)
    except NoResultFound:
        metrics.increment(
            "warehouse.vulnerabilities.error.project_not_found",
            tags=[f"origin:{origin}"],
        )
        raise

    found_releases = False  # by now, we don't have any release found

    for version in report.versions:
        try:
            release = _get_release(request, project, version)
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
        # no releases found, then raise an exception
        raise HTTPBadRequest("None of the releases were found")

    # Unassociate any releases that no longer apply.
    for release in list(vulnerability_record.releases):
        if release.version not in report.versions:
            vulnerability_record.releases.remove(release)


def analyze_vulnerability(request, vulnerability_report, origin, metrics):
    metrics.increment("warehouse.vulnerabilities.received", tags=[f"origin:{origin}"])
    try:
        with metrics.timed(
            "warehouse.vulnerabilities.analysis", tags=[f"origin:{origin}"]
        ):
            _analyze_vulnerability(
                request=request,
                vulnerability_report=vulnerability_report,
                origin=origin,
                metrics=metrics,
            )

        metrics.increment(
            "warehouse.vulnerabilities.processed", tags=[f"origin:{origin}"]
        )
    except (
        vulnerabilities.InvalidVulnerabilityReportError,
        NoResultFound,
        HTTPBadRequest,
    ):
        raise
    except Exception:
        metrics.increment(
            "warehouse.vulnerabilities.error.unknown", tags=[f"origin:{origin}"]
        )
        raise


def analyze_vulnerabilities(request, vulnerability_reports, origin, metrics):
    from warehouse.integrations.vulnerabilities import tasks

    if not isinstance(vulnerability_reports, list):
        metrics.increment(
            "warehouse.vulnerabilities.error.format", tags=[f"origin:{origin}"]
        )
        raise vulnerabilities.InvalidVulnerabilityReportError(
            "Invalid format: payload is not a list", "format"
        )

    for vulnerability_report in vulnerability_reports:
        request.task(tasks.analyze_vulnerability_task).delay(
            vulnerability_report=vulnerability_report,
            origin=origin,
        )
