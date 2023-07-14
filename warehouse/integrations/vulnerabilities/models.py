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


from sqlalchemy import Column, ForeignKey, ForeignKeyConstraint, String, Table, orm
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP

from warehouse import db

release_vulnerabilities = Table(
    "release_vulnerabilities",
    db.metadata,
    Column(
        "release_id",
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "vulnerability_source",
        String,
        nullable=False,
    ),
    Column(
        "vulnerability_id",
        String,
        nullable=False,
    ),
    ForeignKeyConstraint(
        ["vulnerability_source", "vulnerability_id"],
        ["vulnerabilities.source", "vulnerabilities.id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    ),
)


class VulnerabilityRecord(db.ModelBase):
    __tablename__ = "vulnerabilities"

    source = Column(String, primary_key=True)
    id = Column(String, primary_key=True)

    # The URL for the vulnerability report at the source
    # e.g. "https://osv.dev/vulnerability/PYSEC-2021-314"
    link = Column(String)

    # Alternative IDs for this vulnerability
    # e.g. "CVE-2021-12345"
    aliases = Column(ARRAY(String))  # type: ignore[var-annotated]

    # Details about the vulnerability
    details = Column(String)

    # A short, plaintext summary of the vulnerability
    summary = Column(String)

    # Events of introduced/fixed versions
    fixed_in = Column(ARRAY(String))  # type: ignore[var-annotated]

    # When the vulnerability was withdrawn, if it has been withdrawn.
    withdrawn = Column(TIMESTAMP, nullable=True)

    releases = orm.relationship(
        "Release",
        back_populates="vulnerabilities",
        secondary=lambda: release_vulnerabilities,
        passive_deletes=True,
    )
