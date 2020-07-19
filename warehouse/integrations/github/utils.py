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
import re

import attr

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


@attr.s(auto_attribs=True, frozen=True, slots=True)
class TokenLeakDisclosureRequest:

    token: str
    public_url: str

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
                f"Cannot extract token from recieved match", reason="extraction"
            )

        return cls(token=extracted_token, public_url=record["url"])


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
            # TODO Logging something here would be useful in case we recieve
            # unexpected pattern type.
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
            raise InvalidTokenLeakRequest(
                "Invalid format: payload is not a list", "format"
            )
        for disclosure_record in disclosure_records:
            try:
                self.analyze_disclosure(
                    disclosure_record=disclosure_record, origin=origin
                )
            except Exception:
                # TODO log, but don't stop processing other leaks.
                # It seems logger.exception() is not used in the codebase. What is
                # expected ?
                continue
