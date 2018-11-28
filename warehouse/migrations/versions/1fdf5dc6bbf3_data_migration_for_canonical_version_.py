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
"""
Data migration for canonical_version column

Revision ID: 1fdf5dc6bbf3
Revises: f7577b6938c1
Create Date: 2018-02-28 22:40:42.495355
"""

import sqlalchemy as sa

from alembic import op
from packaging.utils import canonicalize_version

revision = "1fdf5dc6bbf3"
down_revision = "f7577b6938c1"

releases = sa.Table(
    "releases",
    sa.MetaData(),
    sa.Column("version", sa.Text(), primary_key=True),
    sa.Column("canonical_version", sa.Text()),
)


def upgrade():
    connection = op.get_bind()
    version_query = sa.select([releases.c.version]).distinct()

    for release in connection.execute(version_query):
        connection.execute(
            releases.update()
            .where(
                sa.and_(
                    releases.c.version == release.version,
                    releases.c.canonical_version.is_(None),
                )
            )
            .values(canonical_version=canonicalize_version(release.version))
        )

    op.alter_column("releases", "canonical_version", nullable=False)


def downgrade():
    raise RuntimeError("No such thing as decanonicalization!")
