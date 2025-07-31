# SPDX-License-Identifier: Apache-2.0

from warehouse import integrations


class InvalidVulnerabilityReportError(Exception):
    def __init__(self, message, reason):
        self.reason = reason
        super().__init__(message)


class VulnerabilityReportRequest:
    def __init__(
        self,
        project: str,
        versions: list[str],
        vulnerability_id: str,
        advisory_link: str,
        aliases: list[str],
        details: str | None,
        summary: str | None,
        fixed_in: list[str],
        withdrawn: str | None,
    ):
        self.project = project
        self.versions = versions
        self.vulnerability_id = vulnerability_id
        self.advisory_link = advisory_link
        self.aliases = aliases
        self.details = details
        self.summary = summary
        self.fixed_in = fixed_in
        self.withdrawn = withdrawn

    @classmethod
    def from_api_request(cls, request):
        if not isinstance(request, dict):
            raise InvalidVulnerabilityReportError(
                f"Record is not a dict but: {str(request)[:100]}", reason="format"
            )

        missing_keys = sorted(
            {"project", "versions", "id", "link", "aliases"} - set(request)
        )
        if missing_keys:
            raise InvalidVulnerabilityReportError(
                f"Record is missing attribute(s): {', '.join(missing_keys)}",
                reason="format",
            )

        return cls(
            project=request["project"],
            versions=request["versions"],
            vulnerability_id=request["id"],
            advisory_link=request["link"],
            aliases=request["aliases"],
            details=request.get("details"),
            summary=request.get("summary"),
            fixed_in=[
                version
                for event in request.get("events", [])
                for event_type, version in event.items()
                if event_type == "fixed"
            ],
            withdrawn=request.get("withdrawn"),
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
