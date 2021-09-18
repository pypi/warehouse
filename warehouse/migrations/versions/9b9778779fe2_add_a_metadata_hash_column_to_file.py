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
Add a metadata_hash column to File

Revision ID: 9b9778779fe2
Revises: 1dbb95161e5a
Create Date: 2021-09-18 07:34:31.828437
"""

import sqlalchemy as sa

from alembic import op

revision = "9b9778779fe2"
down_revision = "1dbb95161e5a"


def upgrade():
    op.add_column("release_files", sa.Column("metadata_hash", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("release_files", "metadata_hash")
