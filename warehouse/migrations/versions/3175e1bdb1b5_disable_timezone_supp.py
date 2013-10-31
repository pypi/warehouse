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
Disable timezone support

Revision ID: 3175e1bdb1b5
Revises: 47e27f268fc2
Create Date: 2013-10-30 21:57:31.502797
"""
from __future__ import absolute_import, division, print_function

# revision identifiers, used by Alembic.
revision = '3175e1bdb1b5'
down_revision = '47e27f268fc2'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column("accounts_user", "last_login", type_=sa.DateTime())
    op.alter_column("accounts_user", "date_joined", type_=sa.DateTime())


def downgrade():
    op.alter_column(
        "accounts_user", "last_login",
        type_=sa.DateTime(timezone=True),
    )
    op.alter_column(
        "accounts_user", "date_joined",
        type_=sa.DateTime(timezone=True),
    )
