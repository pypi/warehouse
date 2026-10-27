# SPDX-License-Identifier: Apache-2.0
"""
Builders for fake-but-well-formed PEP 740 provenance objects.

Objects are constructed through the `pypi_attestations` models (the same
way `warehouse.attestations.services` builds real provenance), and the
embedded certificates are real (self-signed) X.509 certificates carrying
the Fulcio claim OIDs that `PEP740AttestationViewer` decodes, so the
values rendered in the UI stay consistent with the attestation bundle's
publisher. Signatures are placeholders: nothing built here will pass
cryptographic verification.
"""

import base64
import datetime as dt
import json

from functools import lru_cache

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from pyasn1.codec.der.encoder import encode as der_encode
from pyasn1.type.char import UTF8String
from pypi_attestations import (
    Attestation,
    AttestationBundle,
    AttestationType,
    Envelope,
    GitHubPublisher,
    GitLabPublisher,
    GooglePublisher,
    Provenance,
    Publisher,
    TransparencyLogEntry,
    VerificationMaterial,
)


def _publisher_claims(publisher: Publisher, ref: str) -> dict[str, str]:
    """Fulcio claim OIDs matching `publisher`."""
    commit_sha = "d" * 40
    match publisher:
        case GitHubPublisher():
            owner = publisher.repository.split("/", maxsplit=1)[0]
            return {
                "1.3.6.1.4.1.57264.1.8": "https://token.actions.githubusercontent.com",
                "1.3.6.1.4.1.57264.1.11": "github-hosted",
                "1.3.6.1.4.1.57264.1.12": f"https://github.com/{publisher.repository}",
                "1.3.6.1.4.1.57264.1.13": commit_sha,
                "1.3.6.1.4.1.57264.1.14": ref,
                "1.3.6.1.4.1.57264.1.16": f"https://github.com/{owner}",
                "1.3.6.1.4.1.57264.1.18": (
                    f"https://github.com/{publisher.repository}"
                    f"/.github/workflows/{publisher.workflow}@{ref}"
                ),
                "1.3.6.1.4.1.57264.1.19": commit_sha,
                "1.3.6.1.4.1.57264.1.20": "release",
                "1.3.6.1.4.1.57264.1.22": "public",
            }
        case GitLabPublisher():
            owner = publisher.repository.split("/", maxsplit=1)[0]
            return {
                "1.3.6.1.4.1.57264.1.8": "https://gitlab.com",
                "1.3.6.1.4.1.57264.1.11": "gitlab-hosted",
                "1.3.6.1.4.1.57264.1.12": f"https://gitlab.com/{publisher.repository}",
                "1.3.6.1.4.1.57264.1.13": commit_sha,
                "1.3.6.1.4.1.57264.1.14": ref,
                "1.3.6.1.4.1.57264.1.16": f"https://gitlab.com/{owner}",
                "1.3.6.1.4.1.57264.1.18": (
                    f"https://gitlab.com/{publisher.repository}"
                    f"//{publisher.workflow_filepath}@{ref}"
                ),
                "1.3.6.1.4.1.57264.1.19": commit_sha,
                "1.3.6.1.4.1.57264.1.20": "push",
                "1.3.6.1.4.1.57264.1.22": "public",
            }
        case GooglePublisher():  # pragma: no branch
            return {
                "1.3.6.1.4.1.57264.1.8": "https://accounts.google.com",
            }


@lru_cache
def _sign_certificate(claims: tuple[tuple[str, str], ...]) -> bytes:
    """
    A base64-encoded, self-signed certificate carrying Fulcio claim OIDs.

    See: https://github.com/sigstore/fulcio/blob/main/docs/oid-info.md
    """
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "fake-attestation (not sigstore)")]
    )
    now = dt.datetime.now(dt.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + dt.timedelta(minutes=10))
    )
    for oid, value in claims:
        # Claim values are DER-encoded UTF8Strings; pyasn1 ships with
        # pypi-attestations, which uses it to decode these same claims.
        builder = builder.add_extension(
            x509.UnrecognizedExtension(
                x509.ObjectIdentifier(oid), der_encode(UTF8String(value))
            ),
            critical=False,
        )
    cert = builder.sign(key, hashes.SHA256())
    return base64.b64encode(cert.public_bytes(serialization.Encoding.DER))


def fake_certificate(publisher: Publisher, ref: str) -> bytes:
    """Build a fake Fulcio certificate for `publisher` at `ref`."""
    return _sign_certificate(tuple(_publisher_claims(publisher, ref).items()))


def fake_attestation(
    filename: str, sha256: str, predicate_type: str, certificate: bytes
) -> Attestation:
    """A PEP 740 attestation with an in-toto statement envelope."""
    statement: dict = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": filename, "digest": {"sha256": sha256}}],
        "predicateType": predicate_type,
        "predicate": None,
    }
    if predicate_type == AttestationType.SLSA_PROVENANCE_V1:
        statement["predicate"] = {
            "buildDefinition": {
                "buildType": "https://actions.github.io/buildtypes/workflow/v1",
                "externalParameters": {},
            },
            "runDetails": {"builder": {"id": "https://github.com/actions/runner"}},
        }
    return Attestation(
        version=1,
        verification_material=VerificationMaterial(
            certificate=certificate,
            transparency_entries=[
                TransparencyLogEntry(
                    {"logIndex": 424242, "integratedTime": "1750000000"}
                )
            ],
        ),
        envelope=Envelope(
            statement=base64.b64encode(json.dumps(statement).encode()),
            signature=base64.b64encode(b"fake-not-a-real-signature"),
        ),
    )


def fake_provenance(
    filename: str,
    sha256: str,
    predicate_types: list[str],
    repository: str,
    workflow: str,
    version: str,
    publisher: Publisher | None = None,
) -> dict:
    """
    A PEP 740 provenance dict with one bundle.

    The bundle is GitHub-published by default. Pass `publisher` to build a
    bundle (and matching Fulcio certificate claims) for another Trusted
    Publisher.
    """
    resolved_publisher = publisher or GitHubPublisher(
        repository=repository, workflow=workflow, environment="release"
    )
    certificate = fake_certificate(resolved_publisher, f"refs/tags/v{version}")
    return Provenance(
        attestation_bundles=[
            AttestationBundle(
                publisher=resolved_publisher,
                attestations=[
                    fake_attestation(filename, sha256, predicate_type, certificate)
                    for predicate_type in predicate_types
                ],
            )
        ]
    ).model_dump(mode="json")
