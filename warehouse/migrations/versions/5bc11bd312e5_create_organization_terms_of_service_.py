# SPDX-License-Identifier: Apache-2.0
"""
create organization terms of service agreement model

Revision ID: 5bc11bd312e5
Revises: f7720656a33c
Create Date: 2025-01-09 17:58:22.830648
"""

import sqlalchemy as sa

from alembic import op

import warehouse

revision = "5bc11bd312e5"
down_revision = "f7720656a33c"

# Note: It is VERY important to ensure that a migration does not lock for a
#       long period of time and to ensure that each individual migration does
#       not break compatibility with the *previous* version of the code base.
#       This is because the migrations will be ran automatically as part of the
#       deployment process, but while the previous version of the code is still
#       up and running. Thus backwards incompatible changes must be broken up
#       over multiple migrations inside of multiple pull requests in order to
#       phase them in over multiple deploys.
#
#       By default, migrations cannot wait more than 4s on acquiring a lock
#       and each individual statement cannot take more than 5s. This helps
#       prevent situations where a slow migration takes the entire site down.
#
#       If you need to increase this timeout for a migration, you can do so
#       by adding:
#
#           op.execute("SET statement_timeout = 5000")
#           op.execute("SET lock_timeout = 4000")
#
#       To whatever values are reasonable for this migration as part of your
#       migration.


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "organization_terms_of_service_agreements",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("agreed", warehouse.utils.db.types.TZDateTime(), nullable=True),
        sa.Column("notified", warehouse.utils.db.types.TZDateTime(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "organization_terms_of_service_agreements_organization_id_idx",
        "organization_terms_of_service_agreements",
        ["organization_id"],
        unique=False,
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        "organization_terms_of_service_agreements_organization_id_idx",
        table_name="organization_terms_of_service_agreements",
    )
    op.drop_table("organization_terms_of_service_agreements")
    # ### end Alembic commands ###
