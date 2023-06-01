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
Relate Organization and OrganizationApplication

Revision ID: 751a296a089e
Revises: 8248e4ebb067
Create Date: 2023-06-01 01:27:24.951148
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "751a296a089e"
down_revision = "8248e4ebb067"


def upgrade():
    op.add_column(
        "organization_applications",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        None,
        "organization_applications",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )


def downgrade():
    op.drop_constraint(None, "organization_applications", type_="foreignkey")
    op.drop_column("organization_applications", "organization_id")
