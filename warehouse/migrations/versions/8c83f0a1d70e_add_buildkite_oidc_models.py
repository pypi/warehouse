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
Add Buildkite OIDC models

Revision ID: 8c83f0a1d70e
Revises: 186f076eb60b
Create Date: 2023-10-27 09:20:18.030874
"""

import sqlalchemy as sa

from alembic import op

revision = "8c83f0a1d70e"
down_revision = "186f076eb60b"

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
        "buildkite_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_slug", sa.String(), nullable=False),
        sa.Column("pipeline_slug", sa.String(), nullable=False),
        sa.Column("build_branch", sa.String(), nullable=False),
        sa.Column("build_tag", sa.String(), nullable=False),
        sa.Column("step_key", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_slug", "pipeline_slug", name="_buildkite_oidc_publisher_uc"
        ),
    )
    op.create_table(
        "pending_buildkite_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_slug", sa.String(), nullable=False),
        sa.Column("pipeline_slug", sa.String(), nullable=False),
        sa.Column("build_branch", sa.String(), nullable=False),
        sa.Column("build_tag", sa.String(), nullable=False),
        sa.Column("step_key", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_slug",
            "pipeline_slug",
            name="_pending_buildkite_oidc_publisher_uc",
        ),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("pending_buildkite_oidc_publishers")
    op.drop_table("buildkite_oidc_publishers")
    # ### end Alembic commands ###
