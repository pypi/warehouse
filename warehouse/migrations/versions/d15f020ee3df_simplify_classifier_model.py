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
Simplify classifier model

Revision ID: d15f020ee3df
Revises: 6af76ffb9612
Create Date: 2020-02-03 03:28:22.838779
"""

import sqlalchemy as sa

from alembic import op

revision = "d15f020ee3df"
down_revision = "6af76ffb9612"


def upgrade():
    op.drop_column("trove_classifiers", "l4")
    op.drop_column("trove_classifiers", "l5")
    op.drop_column("trove_classifiers", "l3")
    op.drop_column("trove_classifiers", "deprecated")
    op.drop_column("trove_classifiers", "l2")


def downgrade():
    op.add_column(
        "trove_classifiers",
        sa.Column("l2", sa.INTEGER(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "trove_classifiers",
        sa.Column(
            "deprecated",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.add_column(
        "trove_classifiers",
        sa.Column("l3", sa.INTEGER(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "trove_classifiers",
        sa.Column("l5", sa.INTEGER(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "trove_classifiers",
        sa.Column("l4", sa.INTEGER(), autoincrement=False, nullable=True),
    )
