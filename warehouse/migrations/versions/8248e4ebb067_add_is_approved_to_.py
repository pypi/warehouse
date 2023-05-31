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
add is_approved to OrganizationApplication

Revision ID: 8248e4ebb067
Revises: 56e822e126bb
Create Date: 2023-06-01 00:06:39.042021
"""

import sqlalchemy as sa

from alembic import op

revision = "8248e4ebb067"
down_revision = "56e822e126bb"


def upgrade():
    op.add_column(
        "organization_applications",
        sa.Column("is_approved", sa.Boolean(), nullable=True),
    )


def downgrade():
    op.drop_column("organization_applications", "is_approved")
