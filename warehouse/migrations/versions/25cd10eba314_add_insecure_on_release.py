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
Adds insecure and insecure_url to the release table

Revision ID: 25cd10eba314
Revises: f392e419ea1b
Create Date: 2016-01-05 14:44:05.499376
"""

from alembic import op
import sqlalchemy as sa


revision = '25cd10eba314'
down_revision = 'f392e419ea1b'


def upgrade():
    op.add_column(
        "releases",
        sa.Column("insecure", sa.Boolean(), nullable=True),
    )

    op.add_column(
        "releases",
        sa.Column("insecure_url", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("releases", "insecure")
    op.drop_column("releases", "insecure_url")

