# SPDX-License-Identifier: Apache-2.0

import pypi_attestations

from tests.common.db.oidc import GitHubPublisherFactory
from tests.common.db.packaging import FileFactory, ProvenanceFactory


def test_provenance_as_model(db_request, integrity_service, dummy_attestation):
    db_request.oidc_publisher = GitHubPublisherFactory.create()
    file = FileFactory.create()
    provenance = integrity_service.build_provenance(
        db_request, file, [dummy_attestation]
    )

    assert isinstance(provenance.as_model, pypi_attestations.Provenance)


def test_provenance_factory_with_predicate_types(db_request):
    """The factory's fake provenance validates and decodes end to end."""
    file = FileFactory.create(filename="example-1.0.0.tar.gz")
    db_provenance = ProvenanceFactory.create(
        file=file,
        predicate_types=[
            pypi_attestations.AttestationType.PYPI_PUBLISH_V1,
            pypi_attestations.AttestationType.SLSA_PROVENANCE_V1,
        ],
        repository="example-org/example",
        workflow="publish.yml",
    )

    model = db_provenance.as_model
    assert isinstance(model, pypi_attestations.Provenance)
    bundle = model.attestation_bundles[0]
    assert bundle.publisher.repository == "example-org/example"
    assert bundle.publisher.workflow == "publish.yml"
    assert [a.statement["predicateType"] for a in bundle.attestations] == [
        pypi_attestations.AttestationType.PYPI_PUBLISH_V1,
        pypi_attestations.AttestationType.SLSA_PROVENANCE_V1,
    ]
    for attestation in bundle.attestations:
        assert attestation.statement["subject"][0]["name"] == file.filename
        claims = attestation.certificate_claims
        assert (
            claims["1.3.6.1.4.1.57264.1.12"] == "https://github.com/example-org/example"
        )
