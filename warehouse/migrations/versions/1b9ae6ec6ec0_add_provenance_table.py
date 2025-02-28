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
add provenance table

Revision ID: 1b9ae6ec6ec0
Revises: dcf1e3986782
Create Date: 2024-09-03 23:39:30.853147
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "1b9ae6ec6ec0"
down_revision = "dcf1e3986782"


def upgrade():
    op.create_table(
        "provenance",
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column(
            "provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("provenance_digest", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["release_files.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("provenance")
