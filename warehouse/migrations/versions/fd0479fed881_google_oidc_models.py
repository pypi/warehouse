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
Google OIDC models

Revision ID: fd0479fed881
Revises: d1771b942eb6
Create Date: 2023-05-02 17:45:43.772359
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "fd0479fed881"
down_revision = "d1771b942eb6"


def upgrade():
    op.create_table(
        "google_oidc_publishers",
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("sub", sa.String(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", "sub", name="_google_oidc_publisher_uc"),
    )
    op.create_table(
        "pending_google_oidc_publishers",
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("sub", sa.String(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", "sub", name="_pending_google_oidc_publisher_uc"),
    )


def downgrade():
    op.drop_table("pending_google_oidc_publishers")
    op.drop_table("google_oidc_publishers")
