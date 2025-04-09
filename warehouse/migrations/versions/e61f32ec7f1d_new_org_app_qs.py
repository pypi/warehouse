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
Add new questions to the organization application.

Revision ID: e61f32ec7f1d
Revises: d44f083952e4
Create Date: 2025-04-02 18:43:20.147718
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e61f32ec7f1d"
down_revision = "d44f083952e4"


def upgrade():
    sa.Enum(
        "",
        "1",
        "2-5",
        "6-10",
        "11-25",
        "26-50",
        "51-100",
        "100+",
        name="organizationmembershipsize",
    ).create(op.get_bind())
    op.add_column(
        "organization_applications",
        sa.Column(
            "usage",
            sa.String(),
            nullable=True,
            comment="Description of how the applicant plans to use Organizations",
        ),
    )
    op.add_column(
        "organization_applications",
        sa.Column(
            "membership_size",
            postgresql.ENUM(
                "",
                "1",
                "2-5",
                "6-10",
                "11-25",
                "26-50",
                "51-100",
                "100+",
                name="organizationmembershipsize",
                create_type=False,
            ),
            nullable=True,
            comment="Anticipated size of Organization Membership",
        ),
    )


def downgrade():
    op.drop_column("organization_applications", "membership_size")
    op.drop_column("organization_applications", "usage")
    sa.Enum(
        "",
        "1",
        "2-5",
        "6-10",
        "11-25",
        "26-50",
        "51-100",
        "100+",
        name="organizationmembershipsize",
    ).drop(op.get_bind())
