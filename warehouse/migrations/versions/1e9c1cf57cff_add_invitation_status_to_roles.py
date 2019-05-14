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
add_invitation_status_to_roles

Revision ID: 1e9c1cf57cff
Revises: 48def930fcfd
Create Date: 2019-05-08 15:29:16.560240
"""

import sqlalchemy as sa

from alembic import op

revision = "1e9c1cf57cff"
down_revision = "48def930fcfd"


def upgrade():
    op.add_column("roles", sa.Column("invitation_status", sa.Text(), nullable=True))
    op.execute("UPDATE roles SET invitation_status='accepted';")


def downgrade():
    op.drop_column("roles", "invitation_status")
