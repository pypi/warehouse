import collections
import http
from os import environ
from urllib.parse import urlencode

import requests


VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


# flake8: noqa
class RecaptchaError(ValueError): pass
class MissingInputSecretError(RecaptchaError): pass
class InvalidInputSecretError(RecaptchaError): pass
class MissingInputResponseError(RecaptchaError): pass
class InvalidInputResponseError(RecaptchaError): pass
class UnexpectedError(RecaptchaError): pass

ERROR_CODE_MAP = {
    "missing-input-secret": MissingInputSecretError,
    "invalid-input-secret": InvalidInputSecretError,
    "missing-input-response": MissingInputResponseError,
    "invalid-input-response": InvalidInputResponseError,
}

ChallengeResponse = collections.namedtuple(
    "ChallengeResponse", ("challenge_ts", "hostname")
)


class Service:
    def __init__(self, request):
        self.request = request

    @property
    def enabled(self):
        settings = self.request.registry.settings.get("recaptcha", {})
        return len(settings.get("site_key", '')) > 0 and len(
            settings.get("secret_key", "")) > 0

    def verify_response(self, response, remote_ip=None):
        if not self.enabled:
            # TODO: logging
            return

        settings = self.request.registry.settings["recaptcha"]

        payload = {
            "secret": settings["secret_key"],
            "response": response,
        }
        if remote_ip is not None:
            payload["remoteip"] = remote_ip

        # TODO: maybe add a session service? there doesn't seem to be anything
        # calling out to external services atm though
        # TODO: turn verify back on once the certs are fixed
        resp = requests.post(
            VERIFY_URL, urlencode(payload),
            headers={"Content-Type":
                "application/x-www-form-urlencoded; charset=utf-8"},
            verify="/etc/ssl/certs/",
        )
        try:
            data = resp.json()
        except ValueError:
            raise UnexpectedError(
                "Unexpected data in response body: %s" % str(
                    resp.content, 'utf-8')
            )

        try:
            success = data["success"]
        except KeyError:
            raise UnexpectedError(
                "Missing 'success' key in response: %s" % data
            )

        if resp.status_code != http.HTTPStatus.OK or not data["success"]:
            try:
                error_codes = data["error_codes"]
            except KeyError:
                raise UnexpectedError(
                    "Response missing 'error-codes' key: %s" % data
                )
            try:
                exc_tp = ERROR_CODE_MAP[error_codes[0]]
            except KeyError:
                raise UnexpectedError(
                    "Unexpected error code: %s" % error_codes[0]
                )
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

    def add_to_csp_policy(self):
        if not self.enabled:
            # TODO: logging
            return

        csp_service = self.request.find_service(name="csp")
        csp_service["script-src"].extend([
            "https://www.google.com/recaptcha/",
            "https://www.gstatic.com/recaptcha/",
        ])
        csp_service["frame-src"].append(
            "https://www.google.com/recaptcha/",
        )
        csp_service["style-src"].append("'unsafe-inline'")


def service_factory(handler, request):
    return Service(request)


def includeme(config):
    # yeah yeah, binding to a concrete implementation rather than an
    # interface. in a perfect world, this will never be offloaded to another
    # service. however, if it is, then we'll deal with the refactor then
    config.register_service_factory(service_factory, name="recaptcha")

    # key-less recaptcha config will work on localhost, but not prod
    config.add_settings({
        "recaptcha": {
            "site_key": environ.get("RECAPTCHA_SITE_KEY"),
            "secret_key": environ.get("RECAPTCHA_SECRET_KEY"),
        },
    })
