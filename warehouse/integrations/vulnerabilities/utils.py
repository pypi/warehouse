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

import json
import time

from typing import List

import requests

from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound

from warehouse.integrations import verifier
from warehouse.integrations.vulnerabilities.models import VulnerabilityRecord
from warehouse.packaging.models import Project, Release


class InvalidVulnerabilityReportRequest(Exception):
    def __init__(self, message, reason):
        self.reason = reason
        super().__init__(message)


class OSVPublicKeyAPIError(InvalidVulnerabilityReportRequest):
    pass


class VulnerabilityReportRequest:
    def __init__(
        self,
        project: str,
        versions: List[str],
        vulnerability_id: str,
        advisory_link: str,
        aliases: List[str],
    ):
        self.project = project
        self.versions = versions
        self.vulnerability_id = vulnerability_id
        self.advisory_link = advisory_link
        self.aliases = aliases

    @classmethod
    def from_api_request(cls, request):

        if not isinstance(request, dict):
            raise InvalidVulnerabilityReportRequest(
                f"Record is not a dict but: {str(request)[:100]}", reason="format"
            )

        missing_keys = sorted(
            {"project", "versions", "id", "link", "aliases"} - set(request)
        )
        if missing_keys:
            raise InvalidVulnerabilityReportRequest(
                f"Record is missing attribute(s): {', '.join(missing_keys)}",
                reason="format",
            )

        return cls(
            request["project"],
            request["versions"],
            request["id"],
            request["link"],
            request["aliases"],
        )


OSV_PUBLIC_KEYS_URL = "https://osv.dev/public_keys/pypa"
PUBLIC_KEYS_CACHE_TIME = 60 * 30  # 30 minutes
PUBLIC_KEYS_CACHE = verifier.PublicKeysCache(cache_time=PUBLIC_KEYS_CACHE_TIME)


class VulnerabilityVerifier(verifier.PayloadVerifier):
    """
    Checks payload signature using:
    - `requests` for HTTP calls
    - `cryptography` for signature verification
    """

    def __init__(
        self,
        session,
        metrics,
        public_keys_api_url: str = OSV_PUBLIC_KEYS_URL,
        public_keys_cache=PUBLIC_KEYS_CACHE,
    ):
        super().__init__(metrics=metrics, public_keys_cache=public_keys_cache)
        self._session = session
        self._metrics = metrics
        self._public_key_url = public_keys_api_url

    @property
    def metric_name(self):
        return "vulnerabilities.osv"

    def retrieve_public_key_payload(self):
        try:
            response = self._session.get(self._public_key_url)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            raise OSVPublicKeyAPIError(
                f"Invalid response code {response.status_code}: {response.text[:100]}",
                f"public_key_api.status.{response.status_code}",
            ) from exc
        except json.JSONDecodeError as exc:
            raise OSVPublicKeyAPIError(
                f"Non-JSON response received: {response.text[:100]}",
                "public_key_api.invalid_json",
            ) from exc
        except requests.RequestException as exc:
            raise OSVPublicKeyAPIError(
                "Could not connect to GitHub", "public_key_api.network_error"
            ) from exc

    def extract_public_keys(self, pubkey_api_data):
        if not isinstance(pubkey_api_data, dict):
            raise OSVPublicKeyAPIError(
                f"Payload is not a dict but: {str(pubkey_api_data)[:100]}",
                "public_key_api.format_error",
            )
        try:
            public_keys = pubkey_api_data["public_keys"]
        except KeyError:
            raise OSVPublicKeyAPIError(
                "Payload misses 'public_keys' attribute", "public_key_api.format_error"
            )

        if not isinstance(public_keys, list):
            raise OSVPublicKeyAPIError(
                "Payload 'public_keys' attribute is not a list",
                "public_key_api.format_error",
            )

        expected_attributes = {"key", "key_identifier"}
        result = []
        for public_key in public_keys:

            if not isinstance(public_key, dict):
                raise OSVPublicKeyAPIError(
                    f"Key is not a dict but: {public_key}",
                    "public_key_api.format_error",
                )

            attributes = set(public_key)
            if not expected_attributes <= attributes:
                raise OSVPublicKeyAPIError(
                    "Missing attribute in key: "
                    f"{sorted(expected_attributes - attributes)}",
                    "public_key_api.format_error",
                )

            result.append(
                {"key": public_key["key"], "key_id": public_key["key_identifier"]}
            )
        self._public_keys_cache.set(now=time.time(), value=result)
        return result


def _get_project(request, vuln_report: VulnerabilityReportRequest):
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
        .filter(Release.canonical_version == version)
        .one()
    )


def _get_vuln_record(request, vuln_report: VulnerabilityReportRequest, origin):
    return (
        request.db.query(VulnerabilityRecord)
        .filter(VulnerabilityRecord.id == vuln_report.vulnerability_id)
        .filter(VulnerabilityRecord.source == origin)
        .one()
    )


def _delete_vuln_record(request, vuln_record: VulnerabilityRecord):
    request.db.delete(vuln_record)


def _add_vuln_record(request, vuln_record: VulnerabilityRecord):
    request.db.add(vuln_record)


def _analyze_vulnerability(request, vulnerability_report, origin, metrics):
    try:
        report = VulnerabilityReportRequest.from_api_request(
            request=vulnerability_report
        )
    except InvalidVulnerabilityReportRequest as exc:
        metrics.increment(f"warehouse.vulnerabilities.{origin}.error.{exc.reason}")
        raise

    metrics.increment(f"warehouse.vulnerabilities.{origin}.valid")

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
        )
        _add_vuln_record(request, vulnerability_record)

    try:
        project = _get_project(request, report)
    except NoResultFound:
        metrics.increment(f"warehouse.vulnerabilities.{origin}.error.project_not_found")
        raise

    for version in report.versions:
        try:
            release = _get_release(request, project, version)
        except NoResultFound:
            metrics.increment(
                f"warehouse.vulnerabilities.{origin}.error.release_not_found"
            )
            raise

        if release not in vulnerability_record.releases:
            vulnerability_record.releases.append(release)

    # Unassociate any releases that no longer apply.
    for release in list(vulnerability_record.releases):
        if release.canonical_version not in report.versions:
            vulnerability_record.releases.remove(release)


def analyze_vulnerability(request, vulnerability_report, origin, metrics):
    metrics.increment(f"warehouse.vulnerabilities.{origin}.received")
    try:
        _analyze_vulnerability(
            request=request,
            vulnerability_report=vulnerability_report,
            origin=origin,
            metrics=metrics,
        )
        metrics.increment(f"warehouse.vulnerabilities.{origin}.processed")
    except (InvalidVulnerabilityReportRequest, NoResultFound):
        raise
    except Exception:
        metrics.increment(f"warehouse.vulnerabilities.{origin}.error.unknown")
        raise


def analyze_vulnerabilities(request, vulnerability_reports, origin, metrics):
    from warehouse.integrations.vulnerabilities import tasks

    if not isinstance(vulnerability_reports, list):
        metrics.increment(f"warehouse.vulnerabilities.{origin}.error.format")
        raise InvalidVulnerabilityReportRequest(
            "Invalid format: payload is not a list", "format"
        )

    for vulnerability_report in vulnerability_reports:
        request.task(tasks.analyze_vulnerability_task).delay(
            vulnerability_report=vulnerability_report,
            origin=origin,
            metrics=metrics,
        )
