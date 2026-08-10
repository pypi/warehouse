# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import enum
import typing

from dataclasses import dataclass, field
from functools import cached_property
from uuid import UUID

import pydantic
import pypi_attestations
import structlog

from sqlalchemy import ForeignKey, Index, orm
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db

if typing.TYPE_CHECKING:
    from warehouse.packaging.models import File, Release

logger = structlog.get_logger(__name__)


class Provenance(db.Model):
    """
    A table for PEP 740 provenance objects.

    Provenance objects contain one or more attestation objects.
    These attestation objects are grouped into "bundles," each of which
    contains one or more attestations along with the Trusted Publisher
    identity that produced them.
    """

    __tablename__ = "provenance"

    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_files.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    file: Mapped[File] = orm.relationship(back_populates="provenance")

    # This JSONB has the structure of a PEP 740 provenance object.
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, deferred=True)

    @cached_property
    def as_model(self):
        return pypi_attestations.Provenance.model_validate(self.provenance)

    __table_args__ = (Index("ix_provenance_file_id", file_id),)


class ProvenanceState(enum.StrEnum):
    NO_PROVENANCE = "no-provenance"
    FULL_PROVENANCE = "full-provenance"
    PARTIAL_PROVENANCE = "partial-provenance"
    INCONSISTENT_PROVENANCE = "inconsistent-provenance"
    LOST_PROVENANCE = "lost-provenance"
    CHANGED_PROVENANCE = "changed-provenance"


@dataclass(frozen=True)
class PublisherSource:
    """
    A Trusted Publisher identity: what kind it is, and who it is.

    Kept structured rather than flattened into a `"GitHub:foo/bar"` string so
    that a template can branch on `kind` and render `identity` without parsing
    it back apart. `kind` carries the same values as `Publisher.kind` upstream,
    which is what the existing file-details macro already branches on.

    Both fields are immutable strings, so this hashes and can be counted and
    diffed like the plain string it replaces.
    """

    kind: str
    identity: str


@dataclass(frozen=True)
class ProvenanceCounts:
    """
    What one release's files attest to, counted per source and per workflow.

    The mappings are excluded from the hash so that `frozen=True` really does
    mean hashable. They are ordinary dicts, so `frozen` stops the fields being
    reassigned but not the mappings being mutated in place.
    """

    total_files: int
    files_with_provenance: int
    # Files whose provenance is present but could not be parsed, and so
    # contributed no sources. Their publishers are unknown, not absent.
    unreadable_files: int = 0
    source_counts: dict[PublisherSource, int] = field(default_factory=dict, hash=False)
    workflow_counts: dict[str, int] = field(default_factory=dict, hash=False)


@dataclass(frozen=True)
class ProvenanceComparison:
    """The release a status is measured against, and what it attested to."""

    release: Release
    counts: ProvenanceCounts


@dataclass(frozen=True)
class ProvenanceStatus:
    """
    The provenance a Release attests to, and how it compares to its predecessor.

    `comparison` is `None` when there is no release to compare against, and
    populated when there is one, even if that release yielded no identifiable
    sources. Keeping those two cases distinct is what lets the delta
    properties stay silent about releases they know nothing about, rather than
    reporting "nothing changed".
    """

    counts: ProvenanceCounts
    comparison: ProvenanceComparison | None = None

    @cached_property
    def states(self) -> frozenset[ProvenanceState]:
        """Every state this release's provenance is in at once."""
        states = set()
        if self.counts.files_with_provenance == 0:
            states.add(ProvenanceState.NO_PROVENANCE)
        elif self.counts.files_with_provenance == self.counts.total_files:
            states.add(ProvenanceState.FULL_PROVENANCE)
        else:
            states.add(ProvenanceState.PARTIAL_PROVENANCE)

        if len(self.counts.source_counts) > 1 or len(self.counts.workflow_counts) > 1:
            states.add(ProvenanceState.INCONSISTENT_PROVENANCE)

        if self.comparison is not None:
            if (
                self.counts.files_with_provenance == 0
                and self.comparison.counts.files_with_provenance > 0
            ):
                states.add(ProvenanceState.LOST_PROVENANCE)
            elif (
                self.added_sources
                or self.removed_sources
                or self.added_workflows
                or self.removed_workflows
            ):
                states.add(ProvenanceState.CHANGED_PROVENANCE)

        return frozenset(states)

    @property
    def _comparable_counts(self) -> ProvenanceCounts | None:
        """
        The comparison counts, if the two releases can meaningfully be compared.

        A release with an unreadable payload has publishers we cannot see, so
        differences against it would be an artefact of the parse failure
        rather than a real change of publisher.
        """
        if (
            self.comparison is None
            or self.counts.unreadable_files
            or self.comparison.counts.unreadable_files
        ):
            return None
        return self.comparison.counts

    @property
    def added_sources(self) -> set[PublisherSource]:
        if (comparison := self._comparable_counts) is None:
            return set()
        return self.counts.source_counts.keys() - comparison.source_counts.keys()

    @property
    def removed_sources(self) -> set[PublisherSource]:
        if (comparison := self._comparable_counts) is None:
            return set()
        return comparison.source_counts.keys() - self.counts.source_counts.keys()

    @property
    def added_workflows(self) -> set[str]:
        if (comparison := self._comparable_counts) is None:
            return set()
        return self.counts.workflow_counts.keys() - comparison.workflow_counts.keys()

    @property
    def removed_workflows(self) -> set[str]:
        if (comparison := self._comparable_counts) is None:
            return set()
        return comparison.workflow_counts.keys() - self.counts.workflow_counts.keys()


def publisher_source(publisher: pypi_attestations.Publisher) -> PublisherSource:
    """
    Return a Trusted Publisher's identity.

    Carrying the kind keeps publishers of different kinds from being
    conflated: two projects can share a `foo/bar` repository path on GitHub
    and GitLab, and a Google publisher identifies itself by service account
    rather than by repository at all.

    `Publisher` is a closed union, so these arms are exhaustive and there is
    deliberately no fallback: a new publisher kind upstream should fail type
    checking here rather than silently contribute no source.
    """
    match publisher:
        case pypi_attestations.GitHubPublisher() | pypi_attestations.GitLabPublisher():
            return PublisherSource(publisher.kind, publisher.repository)
        case pypi_attestations.GooglePublisher():  # pragma: no branch
            # No fall-through arc exists to cover: mypy rejects this function
            # if the arms above stop being exhaustive.
            return PublisherSource(publisher.kind, publisher.email)


def publisher_workflow(publisher: pypi_attestations.Publisher) -> str | None:
    """
    Return the workflow a Trusted Publisher ran, if it has the concept.

    GitHub and GitLab spell this differently, and Google has no workflow at
    all: it publishes from a service account rather than from a repository.
    """
    match publisher:
        case pypi_attestations.GitHubPublisher():
            return publisher.workflow
        case pypi_attestations.GitLabPublisher():
            return publisher.workflow_filepath
        case _:
            return None


def get_provenance_sources(
    provenance: Provenance,
) -> tuple[set[PublisherSource], set[str]] | None:
    """
    Return the (sources, workflows) a provenance object attests to.

    Sources are kind-prefixed identities; workflows are bare filenames, since
    a workflow is only ever read alongside the source it belongs to.

    Returns `None` when the payload cannot be parsed. That is distinct from a
    payload that parses and names no sources: one unreadable file must not
    take down the release, but neither should it read as a publisher change.
    """
    sources: set[PublisherSource] = set()
    workflows: set[str] = set()

    try:
        model = provenance.as_model
    except pydantic.ValidationError:
        # A row written against a different schema version than the one
        # installed.
        logger.warning(
            "Unparsable provenance",
            provenance_id=provenance.id,
            file_id=provenance.file_id,
        )
        return None

    for bundle in model.attestation_bundles:
        sources.add(publisher_source(bundle.publisher))
        if workflow := publisher_workflow(bundle.publisher):
            workflows.add(workflow)
    return sources, workflows
