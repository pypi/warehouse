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
Add RecoveryCode.burned timestamp

Revision ID: 29a8901a4635
Revises: 0e155b07f096
Create Date: 2022-02-09 00:05:18.323250
"""

import sqlalchemy as sa

from alembic import op

revision = "29a8901a4635"
down_revision = "0e155b07f096"


def upgrade():
    op.add_column(
        "user_recovery_codes", sa.Column("burned", sa.DateTime(), nullable=True)
    )


def downgrade():
    op.drop_column("user_recovery_codes", "burned")
