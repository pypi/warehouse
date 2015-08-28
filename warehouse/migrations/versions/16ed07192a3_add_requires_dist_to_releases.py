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
Add requires_dist to Releases

Revision ID: 16ed07192a3
Revises: 57b1053998d
Create Date: 2015-06-29 19:31:44.196855
"""

from alembic import op
import sqlalchemy as sa


revision = "16ed07192a3"
down_revision = "57b1053998d"


def upgrade():
    op.add_column(
        "releases",
        sa.Column("requires_dist", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("releases", "requires_dist")
