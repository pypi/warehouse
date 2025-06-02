# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, orm
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db

if TYPE_CHECKING:
    from warehouse.packaging.models import Release


class ReleaseVulnerability(db.ModelBase):
    __tablename__ = "release_vulnerabilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["vulnerability_source", "vulnerability_id"],
            ["vulnerabilities.source", "vulnerabilities.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )

    release_id: Mapped[str] = mapped_column(
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
        index=True,
        primary_key=True,
    )
    vulnerability_source: Mapped[str]
    vulnerability_id: Mapped[str]


class VulnerabilityRecord(db.ModelBase):
    __tablename__ = "vulnerabilities"

    source: Mapped[str] = mapped_column(primary_key=True)
    id: Mapped[str] = mapped_column(primary_key=True)

    # The URL for the vulnerability report at the source
    # e.g. "https://osv.dev/vulnerability/PYSEC-2021-314"
    link: Mapped[str | None]

    # Alternative IDs for this vulnerability
    # e.g. "CVE-2021-12345"
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(String))

    # Details about the vulnerability
    details: Mapped[str | None]

    # A short, plaintext summary of the vulnerability
    summary: Mapped[str | None]

    # Events of introduced/fixed versions
    fixed_in: Mapped[list[str] | None] = mapped_column(ARRAY(String))

    # When the vulnerability was withdrawn, if it has been withdrawn.
    withdrawn: Mapped[datetime.datetime | None]

    releases: Mapped[list[Release]] = orm.relationship(
        "Release",
        back_populates="vulnerabilities",
        secondary="release_vulnerabilities",
        passive_deletes=True,
    )
