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
missing migrations for organizations

Revision ID: 760b94e4f1ba
Revises: 6e003184453d
Create Date: 2022-04-25 22:24:55.981645
"""

import sqlalchemy as sa
from alembic import op


revision = "760b94e4f1ba"
down_revision = "6e003184453d"


def upgrade():
    op.alter_column(
        "organization_project",
        "is_active",
        existing_type=sa.BOOLEAN(),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "is_active",
        existing_type=sa.BOOLEAN(),
        server_default=None,
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "organizations",
        "is_active",
        existing_type=sa.BOOLEAN(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )
    op.alter_column(
        "organization_project",
        "is_active",
        existing_type=sa.BOOLEAN(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )
