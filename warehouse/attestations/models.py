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

from pathlib import Path
from uuid import UUID

from sqlalchemy import ForeignKey, orm
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db

if typing.TYPE_CHECKING:
    from warehouse.packaging.models import File


class Attestation(db.Model):
    """
    Table used to store Attestations.

    Attestations are stored on disk. We keep in database only the attestation hash.
    """

    __tablename__ = "attestation"

    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("release_files.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    file: Mapped[File] = orm.relationship(back_populates="attestations")

    attestation_file_blake2_digest: Mapped[str] = mapped_column(CITEXT)

    @hybrid_property
    def attestation_path(self):
        return "/".join(
            [
                self.attestation_file_blake2_digest[:2],
                self.attestation_file_blake2_digest[2:4],
                self.attestation_file_blake2_digest[4:],
                f"{Path(self.file.path).name}.attestation",
            ]
        )
