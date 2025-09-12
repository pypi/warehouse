# SPDX-License-Identifier: Apache-2.0

import http

from urllib.parse import urlencode

from pyramid_retry import RetryableException
from requests.exceptions import Timeout
from zope.interface import implementer

from . import CaptchaError
from .interfaces import ChallengeResponse, ICaptchaService

VERIFY_URL = "https://api.hcaptcha.com/siteverify"


class HCaptchaError(CaptchaError):
    pass


class MissingInputSecretError(HCaptchaError):
    pass


class InvalidInputSecretError(HCaptchaError):
    pass


class MissingInputResponseError(HCaptchaError):
    pass


class InvalidInputResponseError(HCaptchaError):
    pass


class ExpiredInputResponseError(HCaptchaError):
    pass


class AlreadySeenResponseError(HCaptchaError):
    pass


class BadRequestError(HCaptchaError):
    pass


class MissingRemoteIPError(HCaptchaError):
    pass


class InvalidRemoteIPError(HCaptchaError):
    pass


class NotUsingDummyPasscodeError(HCaptchaError):
    pass


class SitekeySecretMismatchError(HCaptchaError):
    pass


class UnexpectedError(HCaptchaError):
    pass


class InvalidOrAlreadySeenResponseError(HCaptchaError):
    pass


# https://docs.hcaptcha.com/#siteverify-error-codes-table
ERROR_CODE_MAP = {
    "missing-input-secret": MissingInputSecretError,
    "invalid-input-secret": InvalidInputSecretError,
    "missing-input-response": MissingInputResponseError,
    "invalid-input-response": InvalidInputResponseError,
    "expired-input-response": ExpiredInputResponseError,
    "already-seen-response": AlreadySeenResponseError,
    "bad-request": BadRequestError,
    "missing-remoteip": MissingRemoteIPError,
    "invalid-remoteip": InvalidRemoteIPError,
    "not-using-dummy-passcode": NotUsingDummyPasscodeError,
    "sitekey-secret-mismatch": SitekeySecretMismatchError,
    # Maybe legacy?
    "invalid-or-already-seen-response": InvalidOrAlreadySeenResponseError,
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
        except Timeout as err:
            raise RetryableException from err
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
