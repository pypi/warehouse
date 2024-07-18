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
from __future__ import annotations

import typing

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    cast,
    func,
    or_,
    orm,
    select,
    sql,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import (
    Mapped,
    attribute_keyed_dict,
    declared_attr,
    mapped_column,
    validates,
)

from warehouse import db

if typing.TYPE_CHECKING:
    from warehouse.packaging.models import File


class ReleaseFileAttestation(db.Model):
    """
    Association table between Release Files and Attestations.

    Attestations are stored as opaque blob because their implementation details are handled by the pypi_attestation package.
    They are linked to release files as a one-to-many relationship.
    """

    __tablename__ = "release_files_attestation"

    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_files.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    file: Mapped[File] = orm.relationship(back_populates="attestations")

    attestation_file_sha256_digest: Mapped[str] = mapped_column(CITEXT)

    @hybrid_property
    def attestation_path(self):
        return self.file.path + self.attestation_file_sha256_digest[:8] + ".attestation"

    @attestation_path.expression  # type: ignore
    def attestation_path(self):
        return func.concat(
            func.concat(
                self.file.path, self.attestation_file_sha256_digest[:8], ".attestation"
            )
        )
