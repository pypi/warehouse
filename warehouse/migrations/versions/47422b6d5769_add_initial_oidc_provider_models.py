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
Add initial OIDC provider models

Revision ID: 47422b6d5769
Revises: 29a8901a4635
Create Date: 2022-02-14 20:45:29.641650
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "47422b6d5769"
down_revision = "29a8901a4635"

# Note: It is VERY important to ensure that a migration does not lock for a
#       long period of time and to ensure that each individual migration does
#       not break compatibility with the *previous* version of the code base.
#       This is because the migrations will be ran automatically as part of the
#       deployment process, but while the previous version of the code is still
#       up and running. Thus backwards incompatible changes must be broken up
#       over multiple migrations inside of multiple pull requests in order to
#       phase them in over multiple deploys.


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "oidc_providers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("discriminator", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "github_oidc_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_name", sa.String(), nullable=True),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("workflow_name", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_providers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("github_oidc_providers")
    op.drop_table("oidc_providers")
    # ### end Alembic commands ###
