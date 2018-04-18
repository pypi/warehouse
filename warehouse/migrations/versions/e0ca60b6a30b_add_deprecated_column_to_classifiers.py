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
Add 'deprecated' column to classifiers

Revision ID: e0ca60b6a30b
Revises: 6714f3f04f0f
Create Date: 2018-04-18 23:24:13.009357
"""

from alembic import op
import sqlalchemy as sa


revision = "e0ca60b6a30b"
down_revision = "6714f3f04f0f"


def upgrade():
    op.add_column(
        "trove_classifiers",
        sa.Column(
            "deprecated",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("trove_classifiers", "deprecated")
