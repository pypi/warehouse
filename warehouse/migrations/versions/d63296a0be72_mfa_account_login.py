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
MFA account login

Revision ID: d63296a0be72
Revises: 3db69c05dd11
Create Date: 2019-02-15 15:45:53.774378
"""

import sqlalchemy as sa

from alembic import op

revision = "d63296a0be72"
down_revision = "3db69c05dd11"


def upgrade():
    op.add_column(
        "users", sa.Column("authentication_seed", sa.String(length=16), nullable=True)
    )


def downgrade():
    op.drop_column("users", "authentication_seed")
