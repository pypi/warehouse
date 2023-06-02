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
create organization and organization_application comments

Revision ID: 89022e31695e
Revises: a423577b60f0
Create Date: 2023-06-02 17:35:22.644363
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "89022e31695e"
down_revision = "a423577b60f0"


def upgrade():
    op.alter_column(
        "organization_applications",
        "name",
        existing_type=sa.TEXT(),
        comment="The account name used in URLS",
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "display_name",
        existing_type=sa.TEXT(),
        comment="Display name used in UI",
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "orgtype",
        existing_type=postgresql.ENUM("Community", "Company", name="organizationtype"),
        comment="What type of organization such as Community or Company",
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "link_url",
        existing_type=sa.TEXT(),
        comment="External URL associated with the organization",
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "description",
        existing_type=sa.TEXT(),
        comment="Description of the business or project the organization represents",
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "is_approved",
        existing_type=sa.BOOLEAN(),
        comment="Status of administrator approval of the request",
        existing_nullable=True,
    )
    op.alter_column(
        "organization_applications",
        "submitted_by_id",
        existing_type=postgresql.UUID(),
        comment="ID of the User which submitted the request",
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "submitted",
        existing_type=postgresql.TIMESTAMP(),
        comment="Datetime the request was submitted",
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "organization_applications",
        "organization_id",
        existing_type=postgresql.UUID(),
        comment="If the request was approved, ID of resulting Organization",
        existing_nullable=True,
    )
    op.alter_column(
        "organizations",
        "name",
        existing_type=sa.TEXT(),
        comment="The account name used in URLS",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "display_name",
        existing_type=sa.TEXT(),
        comment="Display name used in UI",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "orgtype",
        existing_type=sa.TEXT(),
        comment="What type of organization such as Community or Company",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "link_url",
        existing_type=sa.TEXT(),
        comment="External URL associated with the organization",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "description",
        existing_type=sa.TEXT(),
        comment="Description of the business or project the organization represents",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "is_approved",
        existing_type=sa.BOOLEAN(),
        comment="Status of administrator approval of the request",
        existing_nullable=True,
    )
    op.alter_column(
        "organizations",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment="When True, the organization is active and all features are available.",
        existing_nullable=False,
        existing_server_default=sa.text("false"),
    )
    op.alter_column(
        "organizations",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        comment="Datetime the organization was created.",
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "organizations",
        "date_approved",
        existing_type=postgresql.TIMESTAMP(),
        comment="Datetime the organization was approved by administrators.",
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "organizations",
        "date_approved",
        existing_type=postgresql.TIMESTAMP(),
        comment=None,
        existing_comment="Datetime the organization was approved by administrators.",
        existing_nullable=True,
    )
    op.alter_column(
        "organizations",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        comment=None,
        existing_comment="Datetime the organization was created.",
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "organizations",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment=None,
        existing_comment=(
            "When True, the organization is active and all features are available."
        ),
        existing_nullable=False,
        existing_server_default=sa.text("false"),
    )
    op.alter_column(
        "organizations",
        "is_approved",
        existing_type=sa.BOOLEAN(),
        comment=None,
        existing_comment="Status of administrator approval of the request",
        existing_nullable=True,
    )
    op.alter_column(
        "organizations",
        "description",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment=(
            "Description of the business or project the organization represents"
        ),
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "link_url",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="External URL associated with the organization",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "orgtype",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="What type of organization such as Community or Company",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "display_name",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="Display name used in UI",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "name",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="The account name used in URLS",
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "organization_id",
        existing_type=postgresql.UUID(),
        comment=None,
        existing_comment="If the request was approved, ID of resulting Organization",
        existing_nullable=True,
    )
    op.alter_column(
        "organization_applications",
        "submitted",
        existing_type=postgresql.TIMESTAMP(),
        comment=None,
        existing_comment="Datetime the request was submitted",
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "organization_applications",
        "submitted_by_id",
        existing_type=postgresql.UUID(),
        comment=None,
        existing_comment="ID of the User which submitted the request",
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "is_approved",
        existing_type=sa.BOOLEAN(),
        comment=None,
        existing_comment="Status of administrator approval of the request",
        existing_nullable=True,
    )
    op.alter_column(
        "organization_applications",
        "description",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment=(
            "Description of the business or project the organization represents"
        ),
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "link_url",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="External URL associated with the organization",
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "orgtype",
        existing_type=postgresql.ENUM("Community", "Company", name="organizationtype"),
        comment=None,
        existing_comment="What type of organization such as Community or Company",
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "display_name",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="Display name used in UI",
        existing_nullable=False,
    )
    op.alter_column(
        "organization_applications",
        "name",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="The account name used in URLS",
        existing_nullable=False,
    )
