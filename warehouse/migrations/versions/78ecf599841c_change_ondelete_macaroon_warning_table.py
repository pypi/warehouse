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
change_ondelete_macaroon_warning_table

Revision ID: 78ecf599841c
Revises: 444353e3eca2
Create Date: 2024-04-22 15:50:58.878673
"""

import sqlalchemy as sa

from alembic import op

revision = "78ecf599841c"
down_revision = "444353e3eca2"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    conn.execute(sa.text("SET lock_timeout = 120000"))

    op.drop_constraint(
        "project_macaroon_warning_association_project_id_fkey",
        "project_macaroon_warning_association",
        type_="foreignkey",
    )
    op.create_foreign_key(
        None,
        "project_macaroon_warning_association",
        "projects",
        ["project_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(None, "project_macaroon_warning_association", type_="foreignkey")
    op.create_foreign_key(
        "project_macaroon_warning_association_project_id_fkey",
        "project_macaroon_warning_association",
        "projects",
        ["project_id"],
        ["id"],
    )
