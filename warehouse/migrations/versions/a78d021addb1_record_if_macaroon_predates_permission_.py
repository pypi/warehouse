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
Record if a Macaroon predates the permission caveat

Revision ID: a78d021addb1
Revises: 812e14a4cddf
Create Date: 2024-01-20 03:29:32.962023
"""

import sqlalchemy as sa

from alembic import op

revision = "a78d021addb1"
down_revision = "812e14a4cddf"


def upgrade():
    # Initially set our default to true, so all existing macaroons get this set
    # to true, then change it so new macaroons get it set to false.
    op.add_column(
        "macaroons",
        sa.Column(
            "predates_permission_caveat",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.alter_column(
        "macaroons",
        "predates_permission_caveat",
        existing_type=sa.BOOLEAN(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )


def downgrade():
    op.drop_column("macaroons", "predates_permission_caveat")
