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

from sqlalchemy import ForeignKey, orm
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db

if typing.TYPE_CHECKING:
    from warehouse.packaging.models import File


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
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # The Blake2/256 digest of the provenance object stored in this row.
    # Postgres uses a compact binary representation under the hood and is
    # unlikely to provide a permanently stable serialization, so this is the
    # hash of the RFC 8785 serialization.
    provenance_blake2_256_digest: Mapped[str] = mapped_column(CITEXT)
