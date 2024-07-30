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
import datetime
import re

import requests

from cryptography import x509
from cryptography.exceptions import InvalidSignature as _InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA256
from urllib3.util import parse_url

_signing_url_host_re = re.compile(r"^sns\.[a-zA-Z0-9\-]{3,}\.amazonaws\.com(\.cn)?$")


class InvalidMessageError(Exception):
    pass


class MessageVerifier:
    def __init__(self, *, topics, session=None):
        self.topics = topics
        self.http = session if session is not None else requests.session()

    def verify(self, message):
        if message.get("SignatureVersion") == "2":
            self._validate_v2_signature(message)
        else:
            raise InvalidMessageError("Unknown SignatureVersion")

        self._validate_timestamp(message["Timestamp"])
        self._validate_topic(message["TopicArn"])

    def _validate_topic(self, topic):
        if topic not in self.topics:
            raise InvalidMessageError("Invalid TopicArn")

    def _validate_timestamp(self, timestamp_str):
        now = datetime.datetime.now(datetime.UTC)

        try:
            timestamp = datetime.datetime.strptime(
                timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=datetime.UTC)
        except ValueError:
            raise InvalidMessageError("Unknown Timestamp format")

        age = now - timestamp
        if age > datetime.timedelta(hours=1):
            raise InvalidMessageError("Message has expired")

    def _validate_v2_signature(self, message):
        pubkey = self._get_pubkey(message["SigningCertURL"])
        signature = self._get_signature(message)
        data = self._get_data_to_sign(message)

        try:
            pubkey.verify(signature, data, PKCS1v15(), SHA256())
        except _InvalidSignature:
            raise InvalidMessageError("Invalid Signature") from None

    def _get_pubkey(self, cert_url):
        # Before we do anything, we need to verify that the URL for the
        # signature matches what we expect.
        cert_url_p = parse_url(cert_url)
        cert_scheme = cert_url_p.scheme
        cert_host = cert_url_p.netloc
        if cert_scheme != "https":
            raise InvalidMessageError("Invalid scheme for SigningCertURL")
        if _signing_url_host_re.fullmatch(cert_host) is None:
            raise InvalidMessageError("Invalid location for SigningCertURL")

        resp = self.http.get(cert_url)
        resp.raise_for_status()

        cert = x509.load_pem_x509_certificate(resp.content, default_backend())
        return cert.public_key()

    def _get_signature(self, message):
        return base64.b64decode(message["Signature"])

    def _get_data_to_sign(self, message):
        if message["Type"] == "Notification":
            parts = self._get_parts_to_sign_notification(message)
        elif message["Type"] in {"SubscriptionConfirmation", "UnsubscribeConfirmation"}:
            parts = self._get_parts_to_sign_subscription(message)
        else:
            raise InvalidMessageError("Invalid Type")

        return ("\n".join(parts) + "\n").encode("utf8")

    def _get_parts_to_sign_notification(self, message):
        parts = ["Message", message["Message"], "MessageId", message["MessageId"]]

        if "Subject" in message:
            parts.extend(["Subject", message["Subject"]])

        parts.extend(
            [
                "Timestamp",
                message["Timestamp"],
                "TopicArn",
                message["TopicArn"],
                "Type",
                message["Type"],
            ]
        )

        return parts

    def _get_parts_to_sign_subscription(self, message):
        return [
            "Message",
            message["Message"],
            "MessageId",
            message["MessageId"],
            "SubscribeURL",
            message["SubscribeURL"],
            "Timestamp",
            message["Timestamp"],
            "Token",
            message["Token"],
            "TopicArn",
            message["TopicArn"],
            "Type",
            message["Type"],
        ]
