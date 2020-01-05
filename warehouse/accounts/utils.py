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

from warehouse.email import send_password_compromised_email_leak
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.metrics import IMetricsService


class ExtractionFailed(Exception):
    pass


class TokenMatcher:
    def __init__(self, pattern: re.Pattern):
        self.pattern = pattern

    def extract(self, text):
        """
        From a string containing everything that was matched, extract the token
        to check
        """
        return text


class Base64BasicAuthTokenMatcher(TokenMatcher):
    def _extract(self, text):
        # Text is expected to be base64(__token__:pypi-<something>)
        try:
            _, token = base64.b64decode(text).split(":", 1)
            return token
        except Exception as exc:
            raise ExtractionFailed from exc


TOKEN_BREACH_MATCHERS = {
    "token": TokenMatcher(
        # Macaroons are urlsafe_b64 encodeded so non-alphanumeric chars are - and _
        # https://github.com/ecordell/pymacaroons/blob/06b55110eda2fb192c130dee0bcedf8b124d1056/pymacaroons/serializers/binary_serializer.py#L32
        pattern=re.compile(r"pypi-[A-Za-z0-9-_=]+"),
    ),
    # This is what we would expect to find if a basic auth value was leaked
    "base64-basic-auth": Base64BasicAuthTokenMatcher(
        # Basic auth is standard base64, so non-alphanumeric chars are + and /
        # The following string was obtained by:
        #     base64.b64encode(b"__token__:pypi-").decode("utf-8")
        pattern=re.compile(r"X190b2tlbl9fOnB5cGkt[A-Za-z0-9+/=]+"),
    ),
}


class InvalidTokenLeakRequest(Exception):
    def __init__(self, message, reason):
        self.reason = reason
        super().__init__(message)


@attr.s(auto_attribs=True, frozen=True, slots=True)
class TokenLeakDisclosureRequest:

    token: str
    matcher: TokenMatcher
    public_url: str

    @classmethod
    def from_api_record(cls, record, *, matchers=TOKEN_BREACH_MATCHERS):

        if not isinstance(record, dict):
            raise InvalidTokenLeakRequest(
                f"Record is not a dict but: {type(record)}", reason="format"
            )

        try:
            matcher_code = record["type"]
        except KeyError:
            raise InvalidTokenLeakRequest(
                f"Record is missing attribute type", reason="format"
            )

        matcher = matchers.get(matcher_code)
        if not matchers:
            raise InvalidTokenLeakRequest(
                f"Matcher with code {matcher_code} not found. "
                f"Available codes are: {', '.join(matchers)}",
                reason="invalid_matcher",
            )
        try:
            return cls(token=record["token"], matcher=matcher, public_url=record["url"])
        except KeyError as exc:
            raise InvalidTokenLeakRequest(
                f"Record is missing attribute {exc!s}", reason="format"
            )


class TokenLeakAnalyzer:
    def __init__(self, request):
        self._request = request

    def analyze_disclosure(self, disclosure_record, origin):

        metrics = self._request.find_service(IMetricsService, context=None)

        metrics.increment(f"warehouse.token_leak.{origin}.recieved")

        try:
            disclosure = TokenLeakDisclosureRequest.from_api_record(
                record=disclosure_record
            )
        except InvalidTokenLeakRequest as exc:
            metrics.increment(f"warehouse.token_leak.{origin}.error.{exc.reason}")

        # We don't expect to fail at this step: if GitHub starts sending us
        # strings that don't match the regex we have, we have a problem.
        # That being said, except logging, there's not much we can do.
        try:
            token = disclosure.matcher.extract(text=disclosure.token)
        except ExtractionFailed:
            metrics.increment(f"warehouse.token_leak.{origin}.error.extraction")
            return

        macaroon_service = self._request.find_service(IMacaroonService, context=None)

        database_macaroon = macaroon_service.find_macaroon_from_raw(raw_macaroon=token)

        if not database_macaroon:
            metrics.increment(f"warehouse.token_leak.{origin}.invalid")
            return

        metrics.increment(f"warehouse.token_leak.{origin}.valid")
        macaroon_service.delete_macaroon(macaroon_id=str(database_macaroon.id))

        send_password_compromised_email_leak(
            self._request,
            database_macaroon.user,
            public_url=disclosure.public_url,
            origin=origin,
        )
