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
update_name_catalog_to_allow_null_org

Revision ID: d1c00b634ac8
Revises: ad71523546f9
Create Date: 2022-05-11 17:20:56.596019
"""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d1c00b634ac8"
down_revision = "ad71523546f9"

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
    op.alter_column(
        "organization_name_catalog",
        "organization_id",
        existing_type=postgresql.UUID(),
        nullable=True,
    )
    op.create_index(
        op.f("ix_organization_name_catalog_normalized_name"),
        "organization_name_catalog",
        ["normalized_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_name_catalog_organization_id"),
        "organization_name_catalog",
        ["organization_id"],
        unique=False,
    )
    op.drop_constraint(
        "organization_name_catalog_organization_id_fkey",
        "organization_name_catalog",
        type_="foreignkey",
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_foreign_key(
        "organization_name_catalog_organization_id_fkey",
        "organization_name_catalog",
        "organizations",
        ["organization_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.drop_index(
        op.f("ix_organization_name_catalog_organization_id"),
        table_name="organization_name_catalog",
    )
    op.drop_index(
        op.f("ix_organization_name_catalog_normalized_name"),
        table_name="organization_name_catalog",
    )
    op.alter_column(
        "organization_name_catalog",
        "organization_id",
        existing_type=postgresql.UUID(),
        nullable=False,
    )
    # ### end Alembic commands ###
