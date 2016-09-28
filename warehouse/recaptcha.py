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

import collections
import http

from urllib.parse import urlencode


VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


class RecaptchaError(ValueError):
    pass


class MissingInputSecretError(RecaptchaError):
    pass


class InvalidInputSecretError(RecaptchaError):
    pass


class MissingInputResponseError(RecaptchaError):
    pass


class InvalidInputResponseError(RecaptchaError):
    pass


class UnexpectedError(RecaptchaError):
    pass


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
    def csp_policy(self):
        # the use of request.scheme should ever only be for dev. problem is
        # that we use "//" in the script tags, so the request scheme is used.
        # because the csp has to match the script src scheme, it also has to
        # be dynamic.
        return {
            "script-src": [
                "{request.scheme}://www.google.com/recaptcha/",
                "{request.scheme}://www.gstatic.com/recaptcha/",
            ],
            "frame-src": [
                "{request.scheme}://www.google.com/recaptcha/",
            ],
            "style-src": [
                "'unsafe-inline'",
            ],
        }

    @property
    def enabled(self):
        settings = self.request.registry.settings
        return bool(settings.get("recaptcha.site_key") and
                    settings.get("recaptcha.secret_key"))

    def verify_response(self, response, remote_ip=None):
        if not self.enabled:
            # TODO: debug logging
            return

        settings = self.request.registry.settings

        payload = {
            "secret": settings["recaptcha.secret_key"],
            "response": response,
        }
        if remote_ip is not None:
            payload["remoteip"] = remote_ip

        try:
            # TODO: the timeout is hardcoded for now. it would be nice to do
            # something a little more generalized in the future.
            resp = self.request.http.post(
                VERIFY_URL, urlencode(payload),
                headers={"Content-Type":
                         "application/x-www-form-urlencoded; charset=utf-8"},
                timeout=10
            )
        except Exception as err:
            raise UnexpectedError(str(err))

        try:
            data = resp.json()
        except ValueError:
            raise UnexpectedError(
                "Unexpected data in response body: %s" % str(
                    resp.content, 'utf-8')
            )

        if "success" not in data:
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


def service_factory(handler, request):
    return Service(request)


def includeme(config):
    # yeah yeah, binding to a concrete implementation rather than an
    # interface. in a perfect world, this will never be offloaded to another
    # service. however, if it is, then we'll deal with the refactor then
    config.register_service_factory(service_factory, name="recaptcha")
