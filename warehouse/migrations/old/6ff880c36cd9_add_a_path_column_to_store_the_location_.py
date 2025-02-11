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
Add a path column to store the location of the file

Revision ID: 6ff880c36cd9
Revises: f392e419ea1b
Create Date: 2016-01-06 20:37:45.190833
"""

import sqlalchemy as sa

from alembic import op

revision = "6ff880c36cd9"
down_revision = "f392e419ea1b"


def upgrade():
    op.add_column("release_files", sa.Column("path", sa.Text(), nullable=True))
    op.create_unique_constraint(None, "release_files", ["path"])


def downgrade():
    op.drop_constraint(None, "release_files", type_="unique")
    op.drop_column("release_files", "path")
