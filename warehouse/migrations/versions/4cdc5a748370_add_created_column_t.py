# Copyright 2013 Donald Stufft
#
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
Add created column to packages and releases table

Revision ID: 4cdc5a748370
Revises: 77e04097be5
Create Date: 2013-10-24 20:41:22.847711
"""

# revision identifiers, used by Alembic.
revision = "4cdc5a748370"
down_revision = "77e04097be5"

from alembic import op
import sqlalchemy as sa

from warehouse.packaging.tables import packages


def upgrade():
    # Migrate Schema
    op.add_column(
        "packages",
        sa.Column("created", sa.DateTime(), nullable=True),
    )
    op.alter_column("packages", "created", server_default=sa.func.now())

    op.add_column(
        "releases",
        sa.Column("created", sa.DateTime(), nullable=True),
    )
    op.alter_column("releases", "created", server_default=sa.func.now())

    # Backfill data
    op.execute("""
        UPDATE packages AS pkg
        SET created = j.submitted_date
        FROM (
            SELECT name, submitted_date
            FROM journals
            WHERE action = 'create'
        ) j
        WHERE j.name = pkg.name
    """)

    op.execute("""
        UPDATE releases AS r
        SET created = j.submitted_date
        FROM (
            SELECT name, version, max(submitted_date) submitted_date
            FROM journals
            WHERE action = 'new release'
            GROUP BY name, version
        ) j
        WHERE j.name = r.name AND j.version = r.version
    """)

    # Clean up Invalid Data
    op.execute(
        "UPDATE packages SET created = '-infinity' WHERE created IS NULL"
    )
    op.execute(
        "UPDATE releases SET created = '-infinity' WHERE created IS NULL"
    )

    # Modify tables so NULLs are not allowed
    op.alter_column("packages", "created", nullable=False)
    op.alter_column("releases", "created", nullable=False)


def downgrade():
    op.drop_column("packages", "created")
    op.drop_column("releases", "created")
