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
Role.role_name should not be nullable

Revision ID: 6af76ffb9612
Revises: aaa60e8ea12e
Create Date: 2020-03-28 01:20:30.453875
"""

import sqlalchemy as sa

from alembic import op

revision = "6af76ffb9612"
down_revision = "aaa60e8ea12e"


def upgrade():
    op.alter_column("roles", "role_name", existing_type=sa.TEXT(), nullable=False)


def downgrade():
    op.alter_column("roles", "role_name", existing_type=sa.TEXT(), nullable=True)
