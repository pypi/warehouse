# SPDX-License-Identifier: Apache-2.0

import pypi_attestations

from tests.common.db.oidc import GitHubPublisherFactory
from tests.common.db.packaging import FileFactory


def test_provenance_as_model(db_request, integrity_service, dummy_attestation):
    db_request.oidc_publisher = GitHubPublisherFactory.create()
    file = FileFactory.create()
    provenance = integrity_service.build_provenance(
        db_request, file, [dummy_attestation]
    )

    assert isinstance(provenance.as_model, pypi_attestations.Provenance)
