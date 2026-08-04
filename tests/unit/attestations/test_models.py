# SPDX-License-Identifier: Apache-2.0

import pypi_attestations
import pytest

from tests.common.db.oidc import GitHubPublisherFactory
from tests.common.db.packaging import FileFactory, ProvenanceFactory
from warehouse.attestations import models
from warehouse.attestations.models import (
    ProvenanceComparison,
    ProvenanceCounts,
    ProvenanceState,
    ProvenanceStatus,
    PublisherSource,
    get_provenance_sources,
)
from warehouse.packaging.models import Release


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


def _provenance(publisher: pypi_attestations.Publisher | None = None):
    """An unsaved Provenance row carrying one bundle from `publisher`."""
    return ProvenanceFactory.build(
        predicate_types=[pypi_attestations.AttestationType.PYPI_PUBLISH_V1],
        publisher=publisher,
    )


@pytest.mark.parametrize(
    ("publisher", "expected_sources", "expected_workflows"),
    [
        pytest.param(
            pypi_attestations.GitHubPublisher(
                repository="foo/bar", workflow="publish.yml"
            ),
            {PublisherSource("GitHub", "foo/bar")},
            {"publish.yml"},
            id="github",
        ),
        pytest.param(
            pypi_attestations.GitLabPublisher(
                repository="foo/bar", workflow_filepath=".gitlab-ci.yml"
            ),
            {PublisherSource("GitLab", "foo/bar")},
            {".gitlab-ci.yml"},
            id="gitlab",
        ),
        pytest.param(
            pypi_attestations.GooglePublisher(
                email="builder@example.iam.gserviceaccount.com"
            ),
            {PublisherSource("Google", "builder@example.iam.gserviceaccount.com")},
            set(),
            id="google",
        ),
    ],
)
def test_get_provenance_sources_by_publisher_kind(
    publisher, expected_sources, expected_workflows
):
    """
    Every Trusted Publisher contributes an identifiable, kind-prefixed source.

    Google has no repository or workflow, so its service account is the only
    identity it can offer.
    """
    assert get_provenance_sources(_provenance(publisher)) == (
        expected_sources,
        expected_workflows,
    )


def test_get_provenance_sources_distinguishes_kinds_sharing_a_repository():
    """The same repository path on two forges is two distinct sources."""
    github = get_provenance_sources(
        _provenance(
            pypi_attestations.GitHubPublisher(repository="foo/bar", workflow="w.yml")
        )
    )
    gitlab = get_provenance_sources(
        _provenance(
            pypi_attestations.GitLabPublisher(
                repository="foo/bar", workflow_filepath="w.yml"
            )
        )
    )

    assert github is not None
    assert gitlab is not None
    assert github[0] != gitlab[0]


def _counts(**kwargs) -> ProvenanceCounts:
    """Counts for one fully-provenanced GitHub-published file."""
    return ProvenanceCounts(
        **{
            "total_files": 1,
            "files_with_provenance": 1,
            "source_counts": {PublisherSource("GitHub", "foo/bar"): 1},
            "workflow_counts": {"publish.yml": 1},
            **kwargs,
        }
    )


def _comparison(**kwargs) -> ProvenanceComparison:
    """A comparison against a release the delta logic never has to read."""
    return ProvenanceComparison(release=Release(), counts=_counts(**kwargs))


def _status(**kwargs) -> ProvenanceStatus:
    """A status for one fully-provenanced file, overridable per test."""
    return ProvenanceStatus(**{"counts": _counts(), **kwargs})


@pytest.mark.parametrize(
    ("comparison", "expected_added", "expected_removed"),
    [
        pytest.param(None, set(), set(), id="no-comparison-release"),
        pytest.param(
            _comparison(source_counts={}),
            {PublisherSource("GitHub", "foo/bar")},
            set(),
            id="comparison-release-yielded-no-sources",
        ),
        pytest.param(
            _comparison(source_counts={PublisherSource("GitHub", "old/repo"): 1}),
            {PublisherSource("GitHub", "foo/bar")},
            {PublisherSource("GitHub", "old/repo")},
            id="comparison-release-had-a-different-source",
        ),
        pytest.param(
            _comparison(),
            set(),
            set(),
            id="comparison-release-had-the-same-source",
        ),
    ],
)
def test_provenance_status_source_deltas(comparison, expected_added, expected_removed):
    """
    An empty comparison mapping is a real answer, not a missing one.

    A comparison release whose files yield no identifiable sources is
    distinguishable from having no comparison release at all; only the latter
    means "no delta to report".
    """
    status = _status(comparison=comparison)

    assert status.added_sources == expected_added
    assert status.removed_sources == expected_removed


@pytest.mark.parametrize(
    ("comparison", "expected_added", "expected_removed"),
    [
        pytest.param(None, set(), set(), id="no-comparison-release"),
        pytest.param(
            _comparison(workflow_counts={}),
            {"publish.yml"},
            set(),
            id="comparison-release-yielded-no-workflows",
        ),
        pytest.param(
            _comparison(workflow_counts={"old.yml": 1}),
            {"publish.yml"},
            {"old.yml"},
            id="comparison-release-had-a-different-workflow",
        ),
        pytest.param(
            _comparison(),
            set(),
            set(),
            id="comparison-release-had-the-same-workflow",
        ),
    ],
)
def test_provenance_status_workflow_deltas(
    comparison, expected_added, expected_removed
):
    """
    Workflow deltas make the same distinction as source deltas.

    A Google-published comparison release yields sources but no workflows, so
    an empty workflow mapping has to stay distinct from an absent one.
    """
    status = _status(comparison=comparison)

    assert status.added_workflows == expected_added
    assert status.removed_workflows == expected_removed


def test_provenance_status_lost_requires_the_comparison_to_have_had_provenance():
    """
    Nothing is lost if the earlier release never had provenance either.

    `Release.comparison_provenance_release` only returns releases that have
    provenance, but the rule belongs here rather than resting on a join in
    another module.
    """
    status = _status(
        counts=_counts(files_with_provenance=0, source_counts={}, workflow_counts={}),
        comparison=_comparison(
            files_with_provenance=0, source_counts={}, workflow_counts={}
        ),
    )

    assert ProvenanceState.LOST_PROVENANCE not in status.states


def test_provenance_status_is_hashable():
    """`frozen=True` advertises hashability, so the mappings must not break it."""
    status = _status()

    assert hash(status) == hash(_status())
    assert len({status, _status()}) == 1


def test_provenance_status_compares_by_value():
    """Excluding the mappings from the hash must not weaken equality."""
    assert _status() == _status()
    assert _status() != _status(
        counts=_counts(source_counts={PublisherSource("GitHub", "other/repo"): 1})
    )


def test_get_provenance_sources_unparsable_provenance(db_request, mocker):
    """
    An unparsable row reports itself as unreadable instead of raising.

    The row is persisted so that its id and its file's id are distinct real
    values, which is what makes the logged fields worth asserting on.
    """
    log_warning = mocker.patch.object(models.logger, "warning", autospec=True)
    provenance = ProvenanceFactory.create(provenance={"not": "a provenance object"})

    assert get_provenance_sources(provenance) is None

    log_warning.assert_called_once_with(
        "Unparsable provenance",
        provenance_id=provenance.id,
        file_id=provenance.file.id,
    )
