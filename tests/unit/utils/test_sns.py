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
import textwrap

import pretend
import pytest

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)
from cryptography.x509.oid import NameOID

from warehouse.utils.sns import InvalidMessageError, MessageVerifier

VALID_SIGNATURE = object()


@pytest.fixture(scope="module")
def sns_privatekey():
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())


@pytest.fixture(scope="module")
def sns_publickey(sns_privatekey):
    private_key = load_pem_private_key(
        sns_privatekey, password=None, backend=default_backend()
    )
    public_key = private_key.public_key()
    return public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)


@pytest.fixture(scope="module")
def sns_certificate(sns_privatekey, sns_publickey):
    one_day = datetime.timedelta(1, 0, 0)

    private_key = load_pem_private_key(
        sns_privatekey, password=None, backend=default_backend()
    )
    public_key = load_pem_public_key(sns_publickey, backend=default_backend())

    builder = x509.CertificateBuilder()
    builder = builder.subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    )
    builder = builder.issuer_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    )
    builder = builder.not_valid_before(datetime.datetime.today() - one_day)
    builder = builder.not_valid_after(datetime.datetime.today() + one_day)
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.public_key(public_key)
    builder = builder.add_extension(
        x509.SubjectAlternativeName([x509.DNSName("sns.amazonaws.com")]), critical=False
    )
    builder = builder.add_extension(
        x509.BasicConstraints(ca=False, path_length=None), critical=True
    )

    cert = builder.sign(
        private_key=private_key, algorithm=hashes.SHA256(), backend=default_backend()
    )

    return cert.public_bytes(Encoding.PEM)


class TestMessageVerifier:
    @pytest.mark.parametrize(
        ("topics", "data", "error"),
        [
            ([], {}, "Unknown SignatureVersion"),
            ([], {"SignatureVersion": "1"}, "Unknown SignatureVersion"),
            ([], {"SignatureVersion": "3"}, "Unknown SignatureVersion"),
            (
                [],
                {
                    "SignatureVersion": "2",
                    "SigningCertURL": "http://sns.us-west-2.amazonaws.com/cert.pem",
                },
                "Invalid scheme for SigningCertURL",
            ),
            (
                [],
                {
                    "SignatureVersion": "2",
                    "SigningCertURL": "https://sns.us-west-2.attacker.com/cert.pem",
                },
                "Invalid location for SigningCertURL",
            ),
            (
                [],
                {
                    "SignatureVersion": "2",
                    "SigningCertURL": "https://sns.us-west-2.amazonaws.com/cert.pem",
                    "Signature": "SNYwQnC0BxjSo2E4aZFRiA==",
                    "Type": "Who Knows?",
                },
                "Invalid Type",
            ),
            (
                [],
                {
                    "SignatureVersion": "2",
                    "SigningCertURL": "https://sns.us-west-2.amazonaws.com/cert.pem",
                    "Signature": "SNYwQnC0BxjSo2E4aZFRiA==",
                    "Type": "Notification",
                    "Message": "This is My Message",
                    "MessageId": "1",
                    "Timestamp": (
                        datetime.datetime.now(datetime.UTC).strftime(
                            "%Y-%m-%dT%H:%M:%S.%fZ"
                        )
                    ),
                    "TopicArn": "This is My Topic",
                },
                "Invalid Signature",
            ),
            (
                [],
                {
                    "SignatureVersion": "2",
                    "SigningCertURL": "https://sns.us-west-2.amazonaws.com/cert.pem",
                    "Signature": VALID_SIGNATURE,
                    "Type": "Notification",
                    "Message": "This is My Message",
                    "MessageId": "1",
                    "Timestamp": "Wat?",
                    "TopicArn": "This is My Topic",
                },
                "Unknown Timestamp format",
            ),
            (
                [],
                {
                    "SignatureVersion": "2",
                    "SigningCertURL": "https://sns.us-west-2.amazonaws.com/cert.pem",
                    "Signature": VALID_SIGNATURE,
                    "Type": "Notification",
                    "Message": "This is My Message",
                    "MessageId": "1",
                    "Timestamp": (
                        (
                            datetime.datetime.now(datetime.UTC)
                            - datetime.timedelta(days=1)
                        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    ),
                    "TopicArn": "This is My Topic",
                },
                "Message has expired",
            ),
            (
                ["The topic I expected"],
                {
                    "SignatureVersion": "2",
                    "SigningCertURL": "https://sns.us-west-2.amazonaws.com/cert.pem",
                    "Signature": VALID_SIGNATURE,
                    "Type": "Notification",
                    "Message": "This is My Message",
                    "MessageId": "1",
                    "Timestamp": (
                        datetime.datetime.now(datetime.UTC).strftime(
                            "%Y-%m-%dT%H:%M:%S.%fZ"
                        )
                    ),
                    "TopicArn": "This topic I got but didn't expect",
                },
                "Invalid TopicArn",
            ),
        ],
    )
    def test_invalid(self, sns_certificate, sns_privatekey, topics, data, error):
        response = pretend.stub(raise_for_status=lambda: None, content=sns_certificate)
        session = pretend.stub(get=lambda url: response)
        verifier = MessageVerifier(topics=topics, session=session)

        if data.get("Signature") is VALID_SIGNATURE:
            private_key = load_pem_private_key(
                sns_privatekey, password=None, backend=default_backend()
            )
            signature_bytes = private_key.sign(
                verifier._get_data_to_sign(data),
                PKCS1v15(),
                hashes.SHA256(),
            )
            data["Signature"] = base64.b64encode(signature_bytes)

        with pytest.raises(InvalidMessageError, match=error):
            verifier.verify(data)

    @pytest.mark.parametrize(
        ("topics", "data"),
        [
            (
                ["valid topic"],
                {
                    "SignatureVersion": "2",
                    "SigningCertURL": "https://sns.us-west-2.amazonaws.com/cert.pem",
                    "Type": "Notification",
                    "Message": "This is My Message",
                    "MessageId": "1",
                    "Timestamp": (
                        datetime.datetime.now(datetime.UTC).strftime(
                            "%Y-%m-%dT%H:%M:%S.%fZ"
                        )
                    ),
                    "TopicArn": "valid topic",
                },
            ),
            (
                ["valid topic", "another valid topic"],
                {
                    "SignatureVersion": "2",
                    "SigningCertURL": "https://sns.us-west-2.amazonaws.com/cert.pem",
                    "Type": "Notification",
                    "Message": "This is My Message",
                    "MessageId": "1",
                    "Timestamp": (
                        datetime.datetime.now(datetime.UTC).strftime(
                            "%Y-%m-%dT%H:%M:%S.%fZ"
                        )
                    ),
                    "TopicArn": "another valid topic",
                },
            ),
            (
                ["valid topic"],
                {
                    "SignatureVersion": "2",
                    "SigningCertURL": "https://sns.us-west-2.amazonaws.com/cert.pem",
                    "Type": "Notification",
                    "Subject": "This is a subject",
                    "Message": "This is My Message",
                    "MessageId": "1",
                    "Timestamp": (
                        datetime.datetime.now(datetime.UTC).strftime(
                            "%Y-%m-%dT%H:%M:%S.%fZ"
                        )
                    ),
                    "TopicArn": "valid topic",
                },
            ),
            (
                ["valid topic"],
                {
                    "SignatureVersion": "2",
                    "SigningCertURL": "https://sns.us-west-2.amazonaws.com/cert.pem",
                    "Type": "SubscriptionConfirmation",
                    "Message": "This is My Message",
                    "MessageId": "1",
                    "SubscribeURL": "https://example.com/subscribe",
                    "Token": "1234",
                    "Timestamp": (
                        datetime.datetime.now(datetime.UTC).strftime(
                            "%Y-%m-%dT%H:%M:%S.%fZ"
                        )
                    ),
                    "TopicArn": "valid topic",
                },
            ),
        ],
    )
    def test_valid(self, sns_certificate, sns_privatekey, topics, data):
        response = pretend.stub(raise_for_status=lambda: None, content=sns_certificate)
        session = pretend.stub(get=lambda url: response)
        verifier = MessageVerifier(topics=topics, session=session)

        private_key = load_pem_private_key(
            sns_privatekey, password=None, backend=default_backend()
        )
        signature_bytes = private_key.sign(
            verifier._get_data_to_sign(data),
            PKCS1v15(),
            hashes.SHA256(),
        )
        data["Signature"] = base64.b64encode(signature_bytes)

        verifier.verify(data)

    @pytest.mark.parametrize(
        ("data", "expected"),
        [
            (
                {
                    "Type": "SubscriptionConfirmation",
                    "Message": "This is My Message",
                    "MessageId": "1",
                    "SubscribeURL": "https://example.com/subscribe",
                    "Token": "1234",
                    "Timestamp": "2018-04-08T17:01:40.114582Z",
                    "TopicArn": "valid topic",
                },
                """
                Message
                This is My Message
                MessageId
                1
                SubscribeURL
                https://example.com/subscribe
                Timestamp
                2018-04-08T17:01:40.114582Z
                Token
                1234
                TopicArn
                valid topic
                Type
                SubscriptionConfirmation
                """,
            ),
            (
                {
                    "Type": "Notification",
                    "Subject": "This is a subject",
                    "Message": "This is My Message",
                    "MessageId": "1",
                    "Timestamp": "2018-04-08T17:01:40.114582Z",
                    "TopicArn": "valid topic",
                },
                """
                Message
                This is My Message
                MessageId
                1
                Subject
                This is a subject
                Timestamp
                2018-04-08T17:01:40.114582Z
                TopicArn
                valid topic
                Type
                Notification
                """,
            ),
            (
                {
                    "Type": "Notification",
                    "Message": "This is My Message",
                    "MessageId": "1",
                    "Timestamp": "2018-04-08T17:01:40.114582Z",
                    "TopicArn": "valid topic",
                },
                """
                Message
                This is My Message
                MessageId
                1
                Timestamp
                2018-04-08T17:01:40.114582Z
                TopicArn
                valid topic
                Type
                Notification
                """,
            ),
        ],
    )
    def test_signature_data(self, data, expected):
        # We have this method tested specifically, because the above tests
        # don't actually test if this method is functioning correctly,
        # since it uses it for the input and the expected.
        verifier = MessageVerifier(topics=[], session=pretend.stub())
        expected = textwrap.dedent(expected).lstrip().encode("utf8")
        assert verifier._get_data_to_sign(data) == expected
