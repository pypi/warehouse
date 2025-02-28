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
Add canonical_version column

Revision ID: f7577b6938c1
Revises: b75709859292
Create Date: 2018-02-28 15:54:48.867703
"""

import sqlalchemy as sa

from alembic import op

revision = "f7577b6938c1"
down_revision = "b75709859292"


def upgrade():
    op.add_column("releases", sa.Column("canonical_version", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("releases", "canonical_version")
