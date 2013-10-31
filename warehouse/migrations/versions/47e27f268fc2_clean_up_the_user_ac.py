# Copyright 2013 Donald Stufft
#
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
Clean up the user accounts somewhat

Revision ID: 47e27f268fc2
Revises: 4cdc5a748370
Create Date: 2013-10-28 20:57:14.210704
"""
from __future__ import absolute_import, division, print_function

# revision identifiers, used by Alembic.
revision = '47e27f268fc2'
down_revision = '4cdc5a748370'

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade():
    op.alter_column(
        "accounts_user",
        "date_joined",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
        server_default=sa.func.now(),
    )

    # Set anything with a -infinity date_joined to NULL
    op.execute("""
        UPDATE accounts_user
        SET date_joined = NULL
        WHERE date_joined = '-infinity'
    """)


def downgrade():
    # Set anything with a NULL date to -infinity
    op.execute("""
        UPDATE accounts_user
        SET date_joined = NULL
        WHERE date_joined = '-infinity'
    """)

    op.alter_column(
        "accounts_user",
        "date_joined",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
    )
