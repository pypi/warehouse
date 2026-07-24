# SPDX-License-Identifier: Apache-2.0

import pretend
import pypi_attestations

from tests.common.db.oidc import GitHubPublisherFactory
from tests.common.db.packaging import FileFactory
from warehouse.attestations.models import (
    ProvenanceStatus,
    get_file_provenance_sources,
)


def test_provenance_as_model(db_request, integrity_service, dummy_attestation):
    db_request.oidc_publisher = GitHubPublisherFactory.create()
    file = FileFactory.create()
    provenance = integrity_service.build_provenance(
        db_request, file, [dummy_attestation]
    )

    assert isinstance(provenance.as_model, pypi_attestations.Provenance)


def test_get_file_provenance_sources_none():
    file = pretend.stub(provenance=None)
    repos, workflows = get_file_provenance_sources(file)
    assert repos == set()
    assert workflows == set()


def test_get_file_provenance_sources_github():
    file = pretend.stub(
        provenance=pretend.stub(
            as_model=pretend.stub(
                attestation_bundles=[
                    pretend.stub(
                        publisher=pretend.stub(
                            repository="foo/bar", workflow="publish.yml"
                        )
                    )
                ]
            )
        )
    )
    repos, workflows = get_file_provenance_sources(file)
    assert repos == {"foo/bar"}
    assert workflows == {"publish.yml"}


def test_provenance_status_delta_properties_none():
    status = ProvenanceStatus(
        states=set(),
        files_with_provenance=0,
        total_files=0,
        comparison_repository_counts=None,
        comparison_workflow_counts=None,
    )
    assert status.added_repositories == set()
    assert status.removed_repositories == set()
    assert status.added_workflows == set()
    assert status.removed_workflows == set()


def test_get_file_provenance_sources_missing_attrs():
    file = pretend.stub(
        provenance=pretend.stub(
            as_model=pretend.stub(
                attestation_bundles=[
                    pretend.stub(
                        publisher=pretend.stub(
                            repository=None,
                            workflow=None,
                            workflow_filepath=None,
                        )
                    )
                ]
            )
        )
    )
    repos, workflows = get_file_provenance_sources(file)
    assert repos == set()
    assert workflows == set()
