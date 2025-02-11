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
Create composite index for journals

Revision ID: ed4cc2ef6b0f
Revises: 48a7b9ee15af
Create Date: 2025-01-13 19:08:43.774259
"""

import sqlalchemy as sa

from alembic import op

revision = "ed4cc2ef6b0f"
down_revision = "5bc11bd312e5"


def upgrade():
    op.get_bind().commit()
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = 4000")
        op.execute("SET statement_timeout = 5000")
        op.create_index(
            "journals_submitted_by_and_reverse_date_idx",
            "journals",
            ["submitted_by", sa.text("submitted_date DESC")],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index("journals_submitted_by_and_reverse_date_idx", table_name="journals")
