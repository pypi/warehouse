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
import re
import time

from typing import Optional

import requests

from warehouse import integrations
from warehouse.accounts.interfaces import IUserService
from warehouse.email import send_token_compromised_email_leak
from warehouse.macaroons.caveats import InvalidMacaroonError
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.metrics import IMetricsService


class ExtractionFailedError(Exception):
    pass


class TokenLeakMatcher:
    """
    A TokenLeakMatcher is linked to a specific regex pattern. When provided
    a string that matches this pattern, the matcher can extract a token-like string
    from it.
    """

    name: str
    pattern: re.Pattern

    def extract(self, text):
        raise NotImplementedError


class PlainTextTokenLeakMatcher(TokenLeakMatcher):
    name = "pypi_api_token"
    # Macaroons are urlsafe_b64 encodeded so non-alphanumeric chars are - and _
    # https://github.com/ecordell/pymacaroons/blob/06b55110eda2fb192c130dee0bcedf8b124d1056/pymacaroons/serializers/binary_serializer.py#L32
    pattern = re.compile(r"pypi-[A-Za-z0-9-_=]+")

    def extract(self, text):
        """
        From a string containing everything that was matched, extract the token
        to check
        """
        return text


TOKEN_LEAK_MATCHERS = {
    matcher.name: matcher for matcher in [PlainTextTokenLeakMatcher()]
}


class InvalidTokenLeakRequestError(Exception):
    def __init__(self, message, reason):
        self.reason = reason
        super().__init__(message)


class TokenLeakDisclosureRequest:
    def __init__(self, token: str, public_url: str):
        self.token = token
        self.public_url = public_url

    @classmethod
    def from_api_record(cls, record, *, matchers=TOKEN_LEAK_MATCHERS):

        if not isinstance(record, dict):
            raise InvalidTokenLeakRequestError(
                f"Record is not a dict but: {str(record)[:100]}", reason="format"
            )

        missing_keys = sorted({"token", "type", "url"} - set(record))
        if missing_keys:
            raise InvalidTokenLeakRequestError(
                f"Record is missing attribute(s): {', '.join(missing_keys)}",
                reason="format",
            )

        matcher_code = record["type"]

        matcher = matchers.get(matcher_code)
        if not matcher:
            raise InvalidTokenLeakRequestError(
                f"Matcher with code {matcher_code} not found. "
                f"Available codes are: {', '.join(matchers)}",
                reason="invalid_matcher",
            )

        try:
            extracted_token = matcher.extract(record["token"])
        except ExtractionFailedError:
            raise InvalidTokenLeakRequestError(
                "Cannot extract token from recieved match", reason="extraction"
            )

        return cls(token=extracted_token, public_url=record["url"])


class GitHubPublicKeyMetaAPIError(InvalidTokenLeakRequestError):
    pass


PUBLIC_KEYS_CACHE_TIME = 60 * 30  # 30 minutes
PUBLIC_KEYS_CACHE = integrations.PublicKeysCache(cache_time=PUBLIC_KEYS_CACHE_TIME)


class GitHubTokenScanningPayloadVerifier(integrations.PayloadVerifier):
    """
    Checks payload signature using:
    - `requests` for HTTP calls
    - `cryptography` for signature verification
    """

    def __init__(
        self,
        session,
        metrics,
        api_url: str,
        api_token: Optional[str] = None,
        public_keys_cache=PUBLIC_KEYS_CACHE,
    ):
        super().__init__(metrics=metrics, public_keys_cache=public_keys_cache)
        self._session = session
        self._api_token = api_token
        self._api_url = api_url

    @property
    def metric_name(self):
        return "token_leak.github"

    def _headers_auth(self):
        if not self._api_token:
            return {}
        return {"Authorization": f"token {self._api_token}"}

    def retrieve_public_key_payload(self):
        try:
            response = self._session.get(self._api_url, headers=self._headers_auth())
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            raise GitHubPublicKeyMetaAPIError(
                f"Invalid response code {response.status_code}: {response.text[:100]}",
                f"public_key_api.status.{response.status_code}",
            ) from exc
        except json.JSONDecodeError as exc:
            raise GitHubPublicKeyMetaAPIError(
                f"Non-JSON response received: {response.text[:100]}",
                "public_key_api.invalid_json",
            ) from exc
        except requests.RequestException as exc:
            raise GitHubPublicKeyMetaAPIError(
                "Could not connect to GitHub", "public_key_api.network_error"
            ) from exc

    def extract_public_keys(self, pubkey_api_data):
        if not isinstance(pubkey_api_data, dict):
            raise GitHubPublicKeyMetaAPIError(
                f"Payload is not a dict but: {str(pubkey_api_data)[:100]}",
                "public_key_api.format_error",
            )
        try:
            public_keys = pubkey_api_data["public_keys"]
        except KeyError:
            raise GitHubPublicKeyMetaAPIError(
                "Payload misses 'public_keys' attribute", "public_key_api.format_error"
            )

        if not isinstance(public_keys, list):
            raise GitHubPublicKeyMetaAPIError(
                "Payload 'public_keys' attribute is not a list",
                "public_key_api.format_error",
            )

        expected_attributes = {"key", "key_identifier"}
        result = []
        for public_key in public_keys:

            if not isinstance(public_key, dict):
                raise GitHubPublicKeyMetaAPIError(
                    f"Key is not a dict but: {public_key}",
                    "public_key_api.format_error",
                )

            attributes = set(public_key)
            if not expected_attributes <= attributes:
                raise GitHubPublicKeyMetaAPIError(
                    "Missing attribute in key: "
                    f"{sorted(expected_attributes - attributes)}",
                    "public_key_api.format_error",
                )

            result.append(
                {"key": public_key["key"], "key_id": public_key["key_identifier"]}
            )
        self._public_keys_cache.set(now=time.time(), value=result)
        return result


def _analyze_disclosure(request, disclosure_record, origin):

    metrics = request.find_service(IMetricsService, context=None)

    metrics.increment(f"warehouse.token_leak.{origin}.recieved")

    try:
        disclosure = TokenLeakDisclosureRequest.from_api_record(
            record=disclosure_record
        )
    except InvalidTokenLeakRequestError as exc:
        metrics.increment(f"warehouse.token_leak.{origin}.error.{exc.reason}")
        return

    macaroon_service = request.find_service(IMacaroonService, context=None)
    try:
        database_macaroon = macaroon_service.find_from_raw(
            raw_macaroon=disclosure.token
        )
    except InvalidMacaroonError:
        metrics.increment(f"warehouse.token_leak.{origin}.error.invalid")
        return

    metrics.increment(f"warehouse.token_leak.{origin}.valid")

    macaroon_service.delete_macaroon(macaroon_id=str(database_macaroon.id))

    send_token_compromised_email_leak(
        request,
        database_macaroon.user,
        public_url=disclosure.public_url,
        origin=origin,
    )
    user_service = request.find_service(IUserService, context=None)

    user_service.record_event(
        database_macaroon.user.id,
        tag="account:api_token:removed_leak",
        additional={
            "macaroon_id": str(database_macaroon.id),
            "public_url": disclosure.public_url,
            "permissions": database_macaroon.caveats.get("permissions", "user"),
            "description": database_macaroon.description,
        },
    )
    metrics.increment(f"warehouse.token_leak.{origin}.processed")


def analyze_disclosure(request, disclosure_record, origin):
    try:
        _analyze_disclosure(
            request=request,
            disclosure_record=disclosure_record,
            origin=origin,
        )
    except Exception:
        metrics = request.find_service(IMetricsService, context=None)
        metrics.increment(f"warehouse.token_leak.{origin}.error.unknown")
        raise


def analyze_disclosures(request, disclosure_records, origin, metrics):
    from warehouse.integrations.github import tasks

    if not isinstance(disclosure_records, list):
        metrics.increment(f"warehouse.token_leak.{origin}.error.format")
        raise InvalidTokenLeakRequestError(
            "Invalid format: payload is not a list", "format"
        )

    for disclosure_record in disclosure_records:
        request.task(tasks.analyze_disclosure_task).delay(
            disclosure_record=disclosure_record, origin=origin
        )
