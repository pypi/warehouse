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
text

Revision ID: bc8f7b526961
Revises: 19ca1c78e613
Create Date: 2020-06-16 21:14:53.343466
"""

import sqlalchemy as sa

from alembic import op

revision = "bc8f7b526961"
down_revision = "19ca1c78e613"


def upgrade():
    op.add_column(
        "projects", sa.Column("total_size_limit", sa.BigInteger(), nullable=True)
    )


def downgrade():
    op.drop_column("projects", "total_size_limit")
