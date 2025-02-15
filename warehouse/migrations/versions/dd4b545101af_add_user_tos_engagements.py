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
add user tos engagements

Revision ID: dd4b545101af
Revises: 6cac7b706953
Create Date: 2025-02-15 19:17:59.685950
"""

import sqlalchemy as sa

from alembic import op

from warehouse.utils.db.types import TZDateTime

revision = "dd4b545101af"
down_revision = "6cac7b706953"


def upgrade():
    op.create_table(
        "user_terms_of_service_engagements",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("revision", sa.String(), nullable=False),
        sa.Column("viewed", TZDateTime(), nullable=True),
        sa.Column("agreed", TZDateTime(), nullable=True),
        sa.Column("notified", TZDateTime(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "user_terms_of_service_engagements_user_id_idx",
        "user_terms_of_service_engagements",
        ["user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "user_terms_of_service_engagements_user_id_idx",
        table_name="user_terms_of_service_engagements",
    )
    op.drop_table("user_terms_of_service_engagements")
