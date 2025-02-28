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
add size, signature, and docs

Revision ID: 1f002cab0a7
Revises: 283c68f2ab2
Create Date: 2015-06-02 23:50:02.029186
"""

import sqlalchemy as sa

from alembic import op

revision = "1f002cab0a7"
down_revision = "283c68f2ab2"


def upgrade():
    op.add_column("packages", sa.Column("has_docs", sa.Boolean(), nullable=True))

    op.add_column(
        "release_files", sa.Column("has_signature", sa.Boolean(), nullable=True)
    )

    op.add_column("release_files", sa.Column("size", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("release_files", "size")
    op.drop_column("release_files", "has_signature")
    op.drop_column("packages", "has_docs")
