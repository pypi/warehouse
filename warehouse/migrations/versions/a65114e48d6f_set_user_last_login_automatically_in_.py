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
Set User.last_login automatically in the DB

Revision ID: a65114e48d6f
Revises: 104b4c56862b
Create Date: 2016-06-11 00:28:39.176496
"""

import sqlalchemy as sa

from alembic import op

revision = "a65114e48d6f"
down_revision = "104b4c56862b"


def upgrade():
    op.alter_column("accounts_user", "last_login", server_default=sa.func.now())


def downgrade():
    op.alter_column("accounts_user", "last_login", server_default=None)
