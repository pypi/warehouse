# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import enum
import typing

from dataclasses import dataclass, field
from functools import cached_property
from uuid import UUID

import pypi_attestations

from sqlalchemy import ForeignKey, Index, orm
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db

if typing.TYPE_CHECKING:
    from warehouse.packaging.models import File, Release


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
class ProvenanceStatus:
    states: set[ProvenanceState]
    files_with_provenance: int
    total_files: int
    repository_counts: dict[str, int] = field(default_factory=dict)
    workflow_counts: dict[str, int] = field(default_factory=dict)
    comparison_release: Release | None = None
    comparison_files_with_provenance: int | None = None
    comparison_total_files: int | None = None
    comparison_repository_counts: dict[str, int] | None = None
    comparison_workflow_counts: dict[str, int] | None = None

    @property
    def added_repositories(self) -> set[str]:
        if not self.comparison_repository_counts:
            return set()
        return set(self.repository_counts.keys()) - set(
            self.comparison_repository_counts.keys()
        )

    @property
    def removed_repositories(self) -> set[str]:
        if not self.comparison_repository_counts:
            return set()
        return set(self.comparison_repository_counts.keys()) - set(
            self.repository_counts.keys()
        )

    @property
    def added_workflows(self) -> set[str]:
        if not self.comparison_workflow_counts:
            return set()
        return set(self.workflow_counts.keys()) - set(
            self.comparison_workflow_counts.keys()
        )

    @property
    def removed_workflows(self) -> set[str]:
        if not self.comparison_workflow_counts:
            return set()
        return set(self.comparison_workflow_counts.keys()) - set(
            self.workflow_counts.keys()
        )


def get_file_provenance_sources(
    file: File | Provenance,
) -> tuple[set[str], set[str]]:
    """Return (repositories, workflows) sets from an attestation bundle."""
    repositories: set[str] = set()
    workflows: set[str] = set()
    provenance_object = (
        file if hasattr(file, "as_model") else getattr(file, "provenance", None)
    )
    if not provenance_object or not getattr(provenance_object, "as_model", None):
        return repositories, workflows

    model = provenance_object.as_model
    for bundle in model.attestation_bundles:
        publisher = bundle.publisher
        if getattr(publisher, "repository", None):
            repositories.add(publisher.repository)
        workflow = getattr(publisher, "workflow", None) or getattr(
            publisher, "workflow_filepath", None
        )
        if workflow:
            workflows.add(workflow)
    return repositories, workflows
