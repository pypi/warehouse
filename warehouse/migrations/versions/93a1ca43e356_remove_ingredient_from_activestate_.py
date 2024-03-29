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
Remove 'ingredient' from ActiveState Publishing

Revision ID: 93a1ca43e356
Revises: 778f1c01a019
Create Date: 2024-03-13 16:13:44.417966
"""

import sqlalchemy as sa

from alembic import op

revision = "93a1ca43e356"
down_revision = "778f1c01a019"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("activestate_oidc_publishers", "ingredient")
    op.drop_column("pending_activestate_oidc_publishers", "ingredient")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "pending_activestate_oidc_publishers",
        sa.Column("ingredient", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "activestate_oidc_publishers",
        sa.Column("ingredient", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    # ### end Alembic commands ###
