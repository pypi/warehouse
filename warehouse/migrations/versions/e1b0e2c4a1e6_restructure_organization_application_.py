# SPDX-License-Identifier: Apache-2.0
"""
restructure organization application status

Revision ID: e1b0e2c4a1e6
Revises: db7633e75422
Create Date: 2025-03-12 18:43:33.600600
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e1b0e2c4a1e6"
down_revision = "db7633e75422"


def upgrade():
    sa.Enum(
        "submitted",
        "declined",
        "deferred",
        "moreinformationneeded",
        "approved",
        name="organizationapplicationstatus",
    ).create(op.get_bind())
    op.add_column(
        "organization_applications",
        sa.Column(
            "status",
            postgresql.ENUM(
                "submitted",
                "declined",
                "deferred",
                "moreinformationneeded",
                "approved",
                name="organizationapplicationstatus",
                create_type=False,
            ),
            server_default="submitted",
            nullable=False,
            comment="Status of the request",
        ),
    )
    op.execute(
        """ UPDATE organization_applications
            SET status = 'submitted'
            WHERE
                is_approved = NULL
        """
    )
    op.execute(
        """ UPDATE organization_applications
            SET status = 'approved'
            WHERE
                is_approved = TRUE
        """
    )
    op.execute(
        """ UPDATE organization_applications
            SET status = 'declined'
            WHERE
                is_approved = FALSE
        """
    )
    op.add_column(
        "organization_applications",
        sa.Column(
            "updated",
            sa.DateTime(),
            nullable=True,
            comment="Datetime the request was last updated",
        ),
    )
    op.drop_column("organization_applications", "is_approved")
    op.drop_column("organizations", "is_approved")


def downgrade():
    op.add_column(
        "organizations",
        sa.Column(
            "is_approved",
            sa.BOOLEAN(),
            autoincrement=False,
            nullable=True,
            comment="Status of administrator approval of the request",
        ),
    )
    op.add_column(
        "organization_applications",
        sa.Column(
            "is_approved",
            sa.BOOLEAN(),
            autoincrement=False,
            nullable=True,
            comment="Status of administrator approval of the request",
        ),
    )
    op.execute(
        """ UPDATE organization_applications
            SET is_approved = TRUE
            WHERE
                status = 'approved'
        """
    )
    op.execute(
        """ UPDATE organization_applications
            SET is_approved = FALSE
            WHERE
                status = 'declined'
        """
    )
    op.execute(
        """ UPDATE organizations
            SET is_approved = TRUE
        """
    )
    op.drop_column("organization_applications", "updated")
    op.drop_column("organization_applications", "status")
    sa.Enum(
        "submitted",
        "declined",
        "deferred",
        "moreinformationneeded",
        "approved",
        name="organizationapplicationstatus",
    ).drop(op.get_bind())
