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
Add a column for ordering classifiers

Revision ID: 8a335305fd39
Revises: 4490777c984f
Create Date: 2022-07-22 00:06:40.868910
"""

import sqlalchemy as sa

from alembic import op

revision = "8a335305fd39"
down_revision = "4490777c984f"


def upgrade():
    op.add_column(
        "trove_classifiers", sa.Column("ordering", sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column("trove_classifiers", "ordering")
