# SPDX-License-Identifier: Apache-2.0

import json
import time

import requests

from warehouse import integrations
from warehouse.integrations import vulnerabilities


class OSVPublicKeyAPIError(vulnerabilities.InvalidVulnerabilityReportError):
    pass


OSV_PUBLIC_KEYS_URL = "https://osv.dev/public_keys/pypa"
DEFAULT_PUBLIC_KEYS_CACHE_SECONDS = 60 * 30  # 30 minutes
DEFAULT_PUBLIC_KEYS_CACHE = integrations.PublicKeysCache(
    cache_time=DEFAULT_PUBLIC_KEYS_CACHE_SECONDS
)


class VulnerabilityReportVerifier(vulnerabilities.VulnerabilityVerifier):
    def __init__(
        self,
        session,
        metrics,
        public_keys_api_url: str = OSV_PUBLIC_KEYS_URL,
        public_keys_cache=DEFAULT_PUBLIC_KEYS_CACHE,
    ):
        super().__init__(
            metrics=metrics, source="osv", public_keys_cache=public_keys_cache
        )
        self._session = session
        self._metrics = metrics
        self._public_key_url = public_keys_api_url

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
                "Could not connect to OSV", "public_key_api.network_error"
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
