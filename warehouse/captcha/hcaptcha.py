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

import http

from urllib.parse import urlencode

from zope.interface import implementer

from .interfaces import ChallengeResponse, ICaptchaService

VERIFY_URL = "https://api.hcaptcha.com/siteverify"


class HCaptchaError(ValueError):
    pass


class MissingInputSecretError(HCaptchaError):
    pass


class InvalidInputSecretError(HCaptchaError):
    pass


class MissingInputResponseError(HCaptchaError):
    pass


class InvalidInputResponseError(HCaptchaError):
    pass


class BadRequestError(HCaptchaError):
    pass


class InvalidOrAlreadySeenResponseError(HCaptchaError):
    pass


class NotUsingDummyPasscodeError(HCaptchaError):
    pass


class SitekeySecretMismatchError(HCaptchaError):
    pass


class UnexpectedError(HCaptchaError):
    pass


# https://docs.hcaptcha.com/#siteverify-error-codes-table
ERROR_CODE_MAP = {
    "missing-input-secret": MissingInputSecretError,
    "invalid-input-secret": InvalidInputSecretError,
    "missing-input-response": MissingInputResponseError,
    "invalid-input-response": InvalidInputResponseError,
    "invalid-or-already-seen-response": InvalidOrAlreadySeenResponseError,
    "not-using-dummy-passcode": NotUsingDummyPasscodeError,
    "sitekey-secret-mismatch": SitekeySecretMismatchError,
    "bad-request": BadRequestError,
}


_CSP_ENTRIES = [
    "https://hcaptcha.com",
    "https://*.hcaptcha.com",
]


@implementer(ICaptchaService)
class Service:
    def __init__(self, *, request, script_src_url, site_key, secret_key):
        self.request = request
        self.script_src_url = script_src_url
        self.site_key = site_key
        self.secret_key = secret_key
        self.class_name = "h-captcha"

    @classmethod
    def create_service(cls, context, request) -> "Service":
        return cls(
            request=request,
            script_src_url="https://js.hcaptcha.com/1/api.js",
            site_key=request.registry.settings.get("hcaptcha.site_key"),
            secret_key=request.registry.settings.get("hcaptcha.secret_key"),
        )

    @property
    def csp_policy(self) -> dict[str, list[str]]:
        return {
            "script-src": _CSP_ENTRIES,
            "frame-src": _CSP_ENTRIES,
            "style-src": _CSP_ENTRIES,
            "connect-src": _CSP_ENTRIES,
        }

    @property
    def enabled(self) -> bool:
        return bool(self.site_key and self.secret_key)

    def verify_response(self, response, remote_ip=None) -> ChallengeResponse | None:
        if not self.enabled:
            # TODO: debug logging
            return None

        payload = {
            "secret": self.secret_key,
            "response": response,
        }
        if remote_ip is not None:
            payload["remoteip"] = remote_ip

        try:
            # TODO: the timeout is hardcoded for now. it would be nice to do
            # something a little more generalized in the future.
            resp = self.request.http.post(
                VERIFY_URL,
                urlencode(payload),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"
                },
                timeout=10,
            )
        except Exception as err:
            raise UnexpectedError(str(err)) from err

        try:
            data = resp.json()
        except ValueError as e:
            raise UnexpectedError(
                f'Unexpected data in response body: {str(resp.content, "utf-8")}'
            ) from e

        if "success" not in data:
            raise UnexpectedError(f"Missing 'success' key in response: {data}")

        if resp.status_code != http.HTTPStatus.OK or not data["success"]:
            try:
                error_codes = data["error-codes"]
            except KeyError as e:
                raise UnexpectedError(
                    f"Response missing 'error-codes' key: {data}"
                ) from e
            try:
                exc_tp = ERROR_CODE_MAP[error_codes[0]]
            except KeyError as exc:
                raise UnexpectedError(
                    f"Unexpected error code: {error_codes[0]}"
                ) from exc
            raise exc_tp

        # challenge_ts = timestamp of the challenge load
        # (ISO format yyyy-MM-dd'T'HH:mm:ssZZ)
        # TODO: maybe run some validation against the hostname and timestamp?
        # TODO: log if either field is empty.. it shouldn't cause a failure,
        # but it likely means that google has changed their response structure
        return ChallengeResponse(
            data.get("challenge_ts"),
            data.get("hostname"),
        )
