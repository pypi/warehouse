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


from typing import List

import packaging.utils

from warehouse import integrations


class InvalidVulnerabilityReportRequest(Exception):
    def __init__(self, message, reason):
        self.reason = reason
        super().__init__(message)


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
            project=request["project"],
            versions=[
                packaging.utils.canonicalize_version(version)
                for version in request["versions"]
            ],
            vulnerability_id=request["id"],
            advisory_link=request["link"],
            aliases=request["aliases"],
        )


DEFAULT_PUBLIC_KEYS_CACHE_SECONDS = 60 * 30  # 30 minutes
DEFAULT_PUBLIC_KEYS_CACHE = integrations.PublicKeysCache(
    cache_time=DEFAULT_PUBLIC_KEYS_CACHE_SECONDS
)


class VulnerabilityVerifier(integrations.PayloadVerifier):
    def __init__(
        self,
        metrics,
        source: str,
        public_keys_cache=DEFAULT_PUBLIC_KEYS_CACHE,
    ):
        super().__init__(metrics=metrics, public_keys_cache=public_keys_cache)
        self._source = source

    @property
    def metric_name(self):
        return f"vulnerabilities.{self._source}"
