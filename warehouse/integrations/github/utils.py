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

import base64
import json
import re
import time

import requests

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives.hashes import SHA256

from warehouse.email import send_token_compromised_email_leak
from warehouse.macaroons.caveats import InvalidMacaroon
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.metrics import IMetricsService


class ExtractionFailed(Exception):
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
    name = "token"
    # Macaroons are urlsafe_b64 encodeded so non-alphanumeric chars are - and _
    # https://github.com/ecordell/pymacaroons/blob/06b55110eda2fb192c130dee0bcedf8b124d1056/pymacaroons/serializers/binary_serializer.py#L32
    pattern = re.compile(r"pypi-[A-Za-z0-9-_=]+")

    def extract(self, text):
        """
        From a string containing everything that was matched, extract the token
        to check
        """
        return text


class Base64BasicAuthTokenLeakMatcher(TokenLeakMatcher):
    name = "base64-basic-auth"
    # This is what we would expect to find if a basic auth value was leaked
    # The following string was obtained by:
    #     base64.b64encode(b"__token__:pypi-").decode("utf-8")
    # Basic auth is standard base64, so non-alphanumeric chars are + and /
    pattern = re.compile(r"X190b2tlbl9fOnB5cGkt[A-Za-z0-9+/=]+")

    def extract(self, text):
        try:
            _, token = (
                base64.b64decode(text.encode("utf-8")).decode("utf-8").split(":", 1)
            )
            return token
        except Exception as exc:
            raise ExtractionFailed from exc


TOKEN_LEAK_MATCHERS = {
    matcher.name: matcher
    for matcher in [PlainTextTokenLeakMatcher(), Base64BasicAuthTokenLeakMatcher()]
}


class InvalidTokenLeakRequest(Exception):
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
            raise InvalidTokenLeakRequest(
                f"Record is not a dict but: {str(record)[:100]}", reason="format"
            )

        missing_keys = sorted({"token", "type", "url"} - set(record))
        if missing_keys:
            raise InvalidTokenLeakRequest(
                f"Record is missing attribute(s): {', '.join(missing_keys)}",
                reason="format",
            )

        matcher_code = record["type"]

        matcher = matchers.get(matcher_code)
        if not matcher:
            raise InvalidTokenLeakRequest(
                f"Matcher with code {matcher_code} not found. "
                f"Available codes are: {', '.join(matchers)}",
                reason="invalid_matcher",
            )

        try:
            extracted_token = matcher.extract(record["token"])
        except ExtractionFailed:
            raise InvalidTokenLeakRequest(
                "Cannot extract token from recieved match", reason="extraction"
            )

        return cls(token=extracted_token, public_url=record["url"])


class GitHubPublicKeyMetaAPIError(InvalidTokenLeakRequest):
    pass


PUBLIC_KEYS_CACHE_TIME = 60 * 30  # 30 minutes


class GitHubTokenScanningPayloadVerifier:
    """
    Checks payload signature using:
    - `requests` for HTTP calls
    - `cryptography` for signature verification
    """

    def __init__(self, *, session, metrics, api_token):
        self._metrics = metrics
        self._session = session
        self._api_token = api_token

        self.public_keys_cached_at = 0
        self.public_keys_cache = None

    def verify(self, *, payload, key_id, signature):

        try:
            pubkey_api_data = self._retrieve_public_key_payload()
            public_keys = self._extract_public_keys(pubkey_api_data)
            public_key = self._check_public_key(
                github_public_keys=public_keys, key_id=key_id
            )
            self._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )
        except InvalidTokenLeakRequest as exc:
            self._metrics.increment(
                f"warehouse.token_leak.github.auth.error.{exc.reason}"
            )
            return False

        self._metrics.increment("warehouse.token_leak.github.auth.success")
        return True

    def _retrieve_public_key_payload(self):
        if self.public_keys_cached_at + PUBLIC_KEYS_CACHE_TIME < time.time():
            return self.public_keys_cache

        token_scanning_pubkey_api_url = (
            "https://api.github.com/meta/public_keys/secret_scanning"
        )
        headers = {"Authorization": f"token {self._api_token}"}
        try:
            response = self._session.get(token_scanning_pubkey_api_url, headers=headers)
            response.raise_for_status()
            self.public_keys_cache = response.json()
            return self.public_keys_cache
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

    def _extract_public_keys(self, pubkey_api_data):
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

            yield {"key": public_key["key"], "key_id": public_key["key_identifier"]}

        return public_keys

    def _check_public_key(self, github_public_keys, key_id):
        for record in github_public_keys:
            if record["key_id"] == key_id:
                return record["key"]

        raise InvalidTokenLeakRequest(
            f"Key {key_id} not found in github public keys", reason="wrong_key_id"
        )

    def _check_signature(self, payload, public_key, signature):
        try:
            loaded_public_key = serialization.load_pem_public_key(
                data=public_key.encode("utf-8"), backend=default_backend()
            )
            loaded_public_key.verify(
                signature=base64.b64decode(signature),
                data=payload.encode("utf-8"),
                # This validates the ECDSA and SHA256 part
                signature_algorithm=ECDSA(algorithm=SHA256()),
            )
        except InvalidSignature as exc:
            raise InvalidTokenLeakRequest(
                "Invalid signature", "invalid_signature"
            ) from exc
        except Exception as exc:
            # Maybe the key is not a valid ECDSA key, maybe the data is not properly
            # padded, etc. So many things can go wrong...
            raise InvalidTokenLeakRequest(
                "Invalid cryptographic values", "invalid_crypto"
            ) from exc


class TokenLeakAnalyzer:
    def __init__(self, request):
        self._request = request
        self._metrics = self._request.find_service(IMetricsService, context=None)
        self._macaroon_service = self._request.find_service(
            IMacaroonService, context=None
        )

    def analyze_disclosure(self, disclosure_record, origin):

        self._metrics.increment(f"warehouse.token_leak.{origin}.recieved")

        try:
            disclosure = TokenLeakDisclosureRequest.from_api_record(
                record=disclosure_record
            )
        except InvalidTokenLeakRequest as exc:
            self._metrics.increment(f"warehouse.token_leak.{origin}.error.{exc.reason}")
            return

        try:
            database_macaroon = self._macaroon_service.check_if_macaroon_exists(
                raw_macaroon=disclosure.token
            )
        except InvalidMacaroon:
            self._metrics.increment(f"warehouse.token_leak.{origin}.error.invalid")
            return

        self._metrics.increment(f"warehouse.token_leak.{origin}.valid")
        self._macaroon_service.delete_macaroon(macaroon_id=str(database_macaroon.id))

        send_token_compromised_email_leak(
            self._request,
            database_macaroon.user,
            public_url=disclosure.public_url,
            origin=origin,
        )

    def analyze_disclosures(self, disclosure_records, origin):
        if not isinstance(disclosure_records, list):
            self._metrics.increment(f"warehouse.token_leak.{origin}.error.format")
            raise InvalidTokenLeakRequest(
                "Invalid format: payload is not a list", "format"
            )
        for disclosure_record in disclosure_records:
            try:
                self.analyze_disclosure(
                    disclosure_record=disclosure_record, origin=origin
                )
            except Exception:
                self._metrics.increment(f"warehouse.token_leak.{origin}.error")
                continue
            else:
                self._metrics.increment(f"warehouse.token_leak.{origin}.processed")
